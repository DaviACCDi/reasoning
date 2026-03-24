#!/usr/bin/env python3
"""Orchestrate binary subtype calibration with local-model-backed loop."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUBTYPES = ("shift", "rotation", "xor", "and", "or", "not", "mixed")
STATES = (
    "IN_PROGRESS",
    "CALIBRATING",
    "BELOW_THRESHOLD",
    "STABLE",
    "READY_FOR_PR",
    "PR_OPENED",
    "MERGED",
)
SUBTYPE_FOLDERS = ("source", "generated", "validated", "reviewed", "rejected", "final", "reports", "config")

DEFAULT_THRESHOLDS = {
    "min_keep_rate": 0.90,
    "min_semantic_valid_rate": 0.98,
    "min_average_score": 0.95,
    "max_reject_rate": 0.10,
    "stable_rounds_required": 3,
}

PROMPTS_V1: dict[str, str] = {
    "shift": "Generate only hidden-rule tasks using 8-bit shift (left/right, amount 1..3).",
    "rotation": "Generate only hidden-rule tasks using 8-bit rotation (left/right, amount 1..3).",
    "xor": "Generate only hidden-rule tasks using 8-bit XOR with a fixed mask per sample.",
    "and": "Generate only hidden-rule tasks using 8-bit AND with a fixed mask per sample.",
    "or": "Generate only hidden-rule tasks using 8-bit OR with a fixed mask per sample.",
    "not": "Generate only hidden-rule tasks using 8-bit NOT over input bits.",
    "mixed": "Generate only hidden-rule tasks combining exactly two operations among shift/rotation/xor/and/or/not.",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_bin8(n: int) -> str:
    return format(n & 0xFF, "08b")


def apply_rule(value: int, subtype: str, params: dict[str, Any]) -> int:
    op = params["operation"]
    if subtype == "shift":
        amt = int(params["amount"])
        return ((value << amt) & 0xFF) if op == "left_shift" else ((value >> amt) & 0xFF)
    if subtype == "rotation":
        amt = int(params["amount"]) % 8
        if op == "rotate_left":
            return ((value << amt) | (value >> (8 - amt))) & 0xFF
        return ((value >> amt) | (value << (8 - amt))) & 0xFF
    if subtype == "xor":
        return value ^ int(params["mask"])
    if subtype == "and":
        return value & int(params["mask"])
    if subtype == "or":
        return value | int(params["mask"])
    if subtype == "not":
        return (~value) & 0xFF
    if subtype == "mixed":
        first = apply_rule(value, params["first_type"], params["first"])
        return apply_rule(first, params["second_type"], params["second"])
    raise ValueError(subtype)


def random_params(rng: random.Random, subtype: str) -> dict[str, Any]:
    if subtype == "shift":
        return {"operation": rng.choice(["left_shift", "right_shift"]), "amount": rng.randint(1, 3)}
    if subtype == "rotation":
        return {"operation": rng.choice(["rotate_left", "rotate_right"]), "amount": rng.randint(1, 3)}
    if subtype in {"xor", "and", "or"}:
        return {"operation": subtype, "mask": rng.randint(1, 255)}
    if subtype == "not":
        return {"operation": "not"}
    if subtype == "mixed":
        first_type = rng.choice(["shift", "rotation", "xor", "and", "or", "not"])
        second_type = rng.choice(["shift", "rotation", "xor", "and", "or", "not"])
        return {
            "operation": "mixed",
            "first_type": first_type,
            "second_type": second_type,
            "first": random_params(rng, first_type),
            "second": random_params(rng, second_type),
        }
    raise ValueError(subtype)


def local_model_text(model: str, prompt: str, timeout_seconds: int = 45) -> str:
    req_data = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=req_data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return str(body.get("response", "")).strip()
    except Exception:
        return ""


def build_problem(subtype: str, examples: list[tuple[str, str]], query: str) -> str:
    header = f"In Alice's Wonderland, a secret binary {subtype} rule transforms 8-bit inputs."
    lines = [header, "Here are some examples of input -> output:"]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ensure_subtype_layout(root: Path, subtype: str) -> None:
    subtype_root = root / "binary" / subtype
    for folder in SUBTYPE_FOLDERS:
        (subtype_root / folder).mkdir(parents=True, exist_ok=True)
    thresholds_path = subtype_root / "config" / "quality_thresholds.json"
    if not thresholds_path.exists():
        thresholds_path.write_text(
            json.dumps(
                {
                    "subtype": f"binary/{subtype}",
                    "generation_provider": "local",
                    "generation_model": "smollm2:135m",
                    **DEFAULT_THRESHOLDS,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    prompt_v1 = subtype_root / "config" / "prompt_v1.md"
    if not prompt_v1.exists():
        prompt_v1.write_text(PROMPTS_V1[subtype] + "\n", encoding="utf-8")
    pcl = subtype_root / "config" / "prompt_change_log.json"
    if not pcl.exists():
        pcl.write_text(json.dumps([{"version": "v1", "created_at": utc_now(), "note": "Initial prompt"}], indent=2), encoding="utf-8")


def validate_row(subtype: str, row: dict[str, Any]) -> dict[str, Any]:
    validation = {"semantic_valid": True, "format_valid": True, "answer_correct": True, "errors": []}
    if len(str(row["final_answer"])) != 8 or set(str(row["final_answer"])) - {"0", "1"}:
        validation["format_valid"] = False
        validation["errors"].append("format_invalid")
    query = str(row["problem"]).split("Now, determine the output for:")[-1].strip()
    if len(query) != 8 or set(query) - {"0", "1"}:
        validation["semantic_valid"] = False
        validation["errors"].append("invalid_query")
    params = row["metadata"]["params"]
    op = str(params.get("operation", ""))
    allowed_ops = {
        "shift": {"left_shift", "right_shift"},
        "rotation": {"rotate_left", "rotate_right"},
        "xor": {"xor"},
        "and": {"and"},
        "or": {"or"},
        "not": {"not"},
        "mixed": {"mixed"},
    }
    if op not in allowed_ops[subtype]:
        validation["semantic_valid"] = False
        validation["errors"].append(f"forbidden_op:{op}")
    expected = to_bin8(apply_rule(int(query, 2), subtype, row["metadata"]["params"]))
    if expected != row["final_answer"]:
        validation["answer_correct"] = False
        validation["errors"].append("answer_mismatch")
    return validation


def score_row(validation: dict[str, Any]) -> float:
    return round(
        (0.50 if validation["semantic_valid"] else 0.0)
        + (0.30 if validation["format_valid"] else 0.0)
        + (0.20 if validation["answer_correct"] else 0.0),
        6,
    )


def run_iteration(subtype_root: Path, subtype: str, iteration: int, batch_size: int, model: str, rng: random.Random) -> dict[str, Any]:
    guidance_prompt = (
        f"Subtype binary/{subtype}. Provide 1 short writing guideline sentence for clear puzzle phrasing. "
        "No markdown, <= 20 words."
    )
    guidance = local_model_text(model, guidance_prompt)
    guidance = re.sub(r"\s+", " ", guidance).strip()
    guidance = guidance[:160]
    generated: list[dict[str, Any]] = []
    validated: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    reject: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    reject_causes: Counter[str] = Counter()
    review_causes: Counter[str] = Counter()

    for i in range(batch_size):
        params = random_params(rng, subtype)
        examples: list[tuple[str, str]] = []
        for _ in range(5):
            src = rng.randint(0, 255)
            dst = apply_rule(src, subtype, params)
            examples.append((to_bin8(src), to_bin8(dst)))
        q = rng.randint(0, 255)
        row = {
            "id": f"binary_{subtype}_it{iteration:03d}_{i+1:04d}",
            "problem": build_problem(subtype, examples, to_bin8(q)),
            "reasoning": f"Subtype {subtype}: apply one consistent hidden rule to examples and query.",
            "final_answer": to_bin8(apply_rule(q, subtype, params)),
            "metadata": {
                "problem_type": "binary",
                "subgroup": subtype,
                "provider": "local",
                "model": model,
                "local_guidance": guidance,
                "params": params,
                "iteration": iteration,
            },
        }
        generated.append(row)
        validation = validate_row(subtype, row)
        scored = {**row, "validation": validation, "score": score_row(validation)}
        validated.append(scored)
        if validation["semantic_valid"] and validation["format_valid"] and validation["answer_correct"]:
            keep.append(scored)
        elif validation["semantic_valid"]:
            review.append(scored)
            for cause in validation["errors"]:
                review_causes[cause] += 1
        else:
            reject.append(scored)
            for cause in validation["errors"]:
                reject_causes[cause] += 1

    it = f"iteration_{iteration:03d}"
    write_jsonl(subtype_root / "generated" / f"{it}_candidates.jsonl", generated)
    write_jsonl(subtype_root / "validated" / f"{it}_validated.jsonl", validated)
    write_jsonl(subtype_root / "validated" / f"{it}_scored.jsonl", validated)
    write_jsonl(subtype_root / "reviewed" / f"{it}_review.jsonl", review)
    write_jsonl(subtype_root / "rejected" / f"{it}_reject.jsonl", reject)

    m = {
        "keep_rate": round(len(keep) / batch_size, 6),
        "review_rate": round(len(review) / batch_size, 6),
        "reject_rate": round(len(reject) / batch_size, 6),
        "semantic_valid_rate": round(sum(1 for r in validated if r["validation"]["semantic_valid"]) / batch_size, 6),
        "average_score": round(sum(float(r["score"]) for r in validated) / batch_size, 6),
        "reject_causes": dict(reject_causes),
        "review_causes": dict(review_causes),
    }
    (subtype_root / "reports" / f"{it}_quality_report.json").write_text(
        json.dumps({"iteration": iteration, "metrics": m, "generated_at": utc_now()}, indent=2),
        encoding="utf-8",
    )
    return {"metrics": m, "keep_rows": keep}


def export_final(subtype_root: Path, keep_rows: list[dict[str, Any]]) -> None:
    write_jsonl(subtype_root / "final" / "train_ready.jsonl", keep_rows)
    csv_path = subtype_root / "final" / "train_ready.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "prompt", "answer"])
        w.writeheader()
        for row in keep_rows:
            w.writerow({"id": row["id"], "prompt": row["problem"], "answer": row["final_answer"]})
    write_jsonl(subtype_root / "reviewed" / "keep.jsonl", keep_rows)


def create_pr_summary(subtype_root: Path, subtype: str, final_report: dict[str, Any]) -> None:
    summary = {
        "subtype": f"binary/{subtype}",
        "branch": f"feature/binary-{subtype}",
        "state": "READY_FOR_PR",
        "strategy": "Prompt calibration with local model guidance and strict programmatic validator.",
        "metrics": final_report["metrics"],
        "artifacts": [
            "config/prompt_final.md",
            "final/train_ready.jsonl",
            "final/train_ready.csv",
            "reports/final_quality_report.json",
        ],
        "generated_at": utc_now(),
    }
    (subtype_root / "reports" / "merge_request_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_subtype(root: Path, subtype: str, model: str, batch_size: int, max_iterations: int, seed: int) -> dict[str, Any]:
    ensure_subtype_layout(root, subtype)
    st_root = root / "binary" / subtype
    thresholds_raw = json.loads((st_root / "config" / "quality_thresholds.json").read_text(encoding="utf-8"))
    thresholds = thresholds_raw.get("quality_gate", thresholds_raw)
    thresholds = {
        "min_keep_rate": float(thresholds.get("min_keep_rate", DEFAULT_THRESHOLDS["min_keep_rate"])),
        "min_semantic_valid_rate": float(
            thresholds.get("min_semantic_valid_rate", DEFAULT_THRESHOLDS["min_semantic_valid_rate"])
        ),
        "min_average_score": float(thresholds.get("min_average_score", DEFAULT_THRESHOLDS["min_average_score"])),
        "max_reject_rate": float(thresholds.get("max_reject_rate", DEFAULT_THRESHOLDS["max_reject_rate"])),
        "stable_rounds_required": int(
            thresholds.get("stable_rounds_required", DEFAULT_THRESHOLDS["stable_rounds_required"])
        ),
    }

    state = "IN_PROGRESS"
    history: list[dict[str, Any]] = []
    consecutive_passes = 0
    rng = random.Random(seed + hash(subtype) % 10000)
    final_keep: list[dict[str, Any]] = []

    for it in range(1, max_iterations + 1):
        state = "CALIBRATING"
        result = run_iteration(st_root, subtype, it, batch_size, model, rng)
        metrics = result["metrics"]
        passed = (
            metrics["keep_rate"] >= thresholds["min_keep_rate"]
            and metrics["semantic_valid_rate"] >= thresholds["min_semantic_valid_rate"]
            and metrics["average_score"] >= thresholds["min_average_score"]
            and metrics["reject_rate"] <= thresholds["max_reject_rate"]
        )
        history.append({"iteration": it, "metrics": metrics, "passed": passed})
        if passed:
            consecutive_passes += 1
            final_keep = result["keep_rows"]
            if consecutive_passes >= thresholds["stable_rounds_required"]:
                state = "STABLE"
                break
        else:
            consecutive_passes = 0
            state = "BELOW_THRESHOLD"

        # Prompt revision trail per iteration.
        pv = st_root / "config" / f"prompt_v{it + 1}.md"
        pv.write_text(
            f"{PROMPTS_V1[subtype]}\n\nCalibration note: iteration {it} => "
            f"keep={metrics['keep_rate']} reject={metrics['reject_rate']} score={metrics['average_score']}\n",
            encoding="utf-8",
        )
        pcl = json.loads((st_root / "config" / "prompt_change_log.json").read_text(encoding="utf-8"))
        pcl.append({"version": f"v{it+1}", "created_at": utc_now(), "note": f"Auto-calibration from iteration {it}"})
        (st_root / "config" / "prompt_change_log.json").write_text(json.dumps(pcl, indent=2), encoding="utf-8")

    if state == "STABLE":
        (st_root / "config" / "prompt_final.md").write_text(
            (st_root / "config" / "prompt_v1.md").read_text(encoding="utf-8")
            + "\nFinalized after stable rounds.\n",
            encoding="utf-8",
        )
        export_final(st_root, final_keep)
        state = "READY_FOR_PR"

    final_report = {"subtype": f"binary/{subtype}", "state": state, "history": history, "metrics": (history[-1]["metrics"] if history else {})}
    (st_root / "reports" / "calibration_summary.json").write_text(json.dumps(final_report, indent=2), encoding="utf-8")
    (st_root / "reports" / "final_quality_report.json").write_text(json.dumps(final_report, indent=2), encoding="utf-8")
    if state == "READY_FOR_PR":
        create_pr_summary(st_root, subtype, final_report)
    return final_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestrate binary subtype calibration loop.")
    parser.add_argument("--model", default="smollm2:135m")
    parser.add_argument("--provider", default="local")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--subtypes", default="all", help="Comma-separated subtypes or 'all'")
    parser.add_argument("--root", default="data/subtypes")
    args = parser.parse_args()

    if args.provider != "local":
        raise ValueError("This orchestrator supports only local provider.")

    chosen = SUBTYPES if args.subtypes == "all" else tuple(x.strip() for x in args.subtypes.split(",") if x.strip())
    root = Path(args.root)
    overall: dict[str, Any] = {"provider": args.provider, "model": args.model, "started_at": utc_now(), "states": list(STATES), "subtypes": {}}

    for subtype in chosen:
        overall["subtypes"][subtype] = run_subtype(root, subtype, args.model, args.batch_size, args.max_iterations, args.seed)

    overall["finished_at"] = utc_now()
    overall_path = root / "binary" / "reports_orchestrator.json"
    overall_path.parent.mkdir(parents=True, exist_ok=True)
    overall_path.write_text(json.dumps(overall, indent=2), encoding="utf-8")
    print(f"Orchestrator report: {overall_path}")
    for k, v in overall["subtypes"].items():
        print(f"{k}: {v['state']}")


if __name__ == "__main__":
    main()
