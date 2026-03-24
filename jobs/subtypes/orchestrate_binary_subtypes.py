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
    "min_adversarial_detection_rate": 0.95,
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
        # Phase 1: exactly two operations per sample.
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


def normalize_final_answer(text: str) -> str:
    value = str(text).strip()
    boxed = re.fullmatch(r"\\boxed\{([01]{8})\}", value)
    if boxed:
        return boxed.group(1)
    return value


def build_problem(subtype: str, examples: list[tuple[str, str]], query: str) -> str:
    header = f"In Alice's Wonderland, a secret binary {subtype} rule transforms 8-bit inputs."
    lines = [header, "Here are some examples of input -> output:"]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def build_shift_problem_train_style(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def build_rotation_problem_train_style(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def build_xor_problem_train_style(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def build_and_problem_train_style(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def build_or_problem_train_style(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def build_not_problem_train_style(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def build_mixed_problem_train_style(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
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
    normalized_answer = normalize_final_answer(str(row["final_answer"]))
    if len(normalized_answer) != 8 or set(normalized_answer) - {"0", "1"}:
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
    if subtype in {"shift", "rotation", "xor", "and", "or", "not", "mixed"}:
        lines = str(row["problem"]).splitlines()
        sample_pairs: list[tuple[str, str]] = []
        for line in lines:
            m = re.fullmatch(r"([01]{8}) -> ([01]{8})", line.strip())
            if m:
                sample_pairs.append((m.group(1), m.group(2)))
        if len(sample_pairs) < 3:
            validation["semantic_valid"] = False
            validation["errors"].append("insufficient_examples")
        else:
            for src, dst in sample_pairs:
                expected_dst = to_bin8(apply_rule(int(src, 2), subtype, row["metadata"]["params"]))
                if expected_dst != dst:
                    validation["semantic_valid"] = False
                    validation["errors"].append("example_rule_mismatch")
                    break
    if validation["semantic_valid"] and len(query) == 8 and not (set(query) - {"0", "1"}):
        expected = to_bin8(apply_rule(int(query, 2), subtype, row["metadata"]["params"]))
        if expected != normalized_answer:
            validation["answer_correct"] = False
            validation["errors"].append("answer_mismatch")
    else:
        validation["answer_correct"] = False
        validation["errors"].append("answer_unverifiable")
    return validation


def score_row(validation: dict[str, Any]) -> float:
    return round(
        (0.50 if validation["semantic_valid"] else 0.0)
        + (0.30 if validation["format_valid"] else 0.0)
        + (0.20 if validation["answer_correct"] else 0.0),
        6,
    )


def force_wrong_answer(bits: str) -> str:
    if len(bits) != 8 or set(bits) - {"0", "1"}:
        return "00000000"
    first = "1" if bits[0] == "0" else "0"
    return first + bits[1:]


def parse_first_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def strict_json_parse(text: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(text)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if set(obj.keys()) != {"problem", "reasoning", "final_answer"}:
        return None
    return obj


def safe_repair_json(raw: str) -> tuple[dict[str, Any] | None, str]:
    extracted = parse_first_json_object(raw)
    if extracted and set(extracted.keys()) >= {"problem", "reasoning", "final_answer"}:
        return (
            {
                "problem": str(extracted["problem"]),
                "reasoning": str(extracted["reasoning"]),
                "final_answer": str(extracted["final_answer"]),
            },
            "extract_object",
        )

    # Controlled trivial repair: single quotes to double quotes for a full object-like span.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1].strip()
        if '"' not in candidate and "'" in candidate:
            repaired = candidate.replace("'", '"')
            parsed = strict_json_parse(repaired)
            if parsed:
                return parsed, "single_quote_fix"
            return None, "unsafe_single_quote_fix_failed"
    return None, "unrepairable"


def local_generate_sample(
    model: str,
    subtype: str,
    examples: list[tuple[str, str]],
    query: str,
    params: dict[str, Any],
    strict_local_generation: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    if subtype == "shift":
        shift_dir = "left" if params.get("operation") == "left_shift" else "right"
        shift_amount = int(params.get("amount", 1))
        example_lines = "\\n".join([f"{src} -> {dst}" for src, dst in examples])
        prompt = (
            "Return ONLY valid JSON. No prose outside JSON. Use exactly keys problem,reasoning,final_answer.\n"
            "Schema: {\"problem\":\"...\",\"reasoning\":\"...\",\"final_answer\":\"\\\\boxed{xxxxxxxx}\"}\n"
            "STRICT problem template:\n"
            "In Alice's Wonderland, a secret binary shift rule transforms 8-bit inputs.\\n"
            "Apply a "
            f"{shift_dir} shift by {shift_amount} positions.\\n"
            "Here are some examples of input -> output:\\n"
            f"{example_lines}\\n\\n"
            f"Now, determine the output for: {query}\n"
            "STRICT reasoning template:\n"
            f"\"A {shift_dir} shift by {shift_amount} moves bits {shift_amount} positions and fills with 0. "
            "Applying it to the query yields the final output.\"\n"
            "final_answer must be exactly 8 bits inside \\boxed{}."
        )
    else:
        prompt = (
            "Return ONLY this JSON object with exactly 3 keys and no extra text:\n"
            '{"problem":"...","reasoning":"...","final_answer":"\\\\boxed{xxxxxxxx}"}\n'
            f"Subtype={subtype}; Query={query}; Params={params}; Examples={examples}"
        )
    raw = local_model_text(model, prompt, timeout_seconds=12)
    parsed = strict_json_parse(raw)
    if parsed:
        return (
            {
                "problem": str(parsed["problem"]),
                "reasoning": str(parsed["reasoning"]),
                "final_answer": str(parsed["final_answer"]),
            },
            {"raw_parse_success": True, "repaired_parse_success": False, "unsafe_repair": False, "repair_method": "none"},
        )

    repaired, method = safe_repair_json(raw)
    if repaired:
        return (
            {
                "problem": str(repaired["problem"]),
                "reasoning": str(repaired["reasoning"]),
                "final_answer": str(repaired["final_answer"]),
            },
            {"raw_parse_success": False, "repaired_parse_success": True, "unsafe_repair": False, "repair_method": method},
        )

    unsafe = method.startswith("unsafe_")
    if strict_local_generation:
        return (
            {"problem": "", "reasoning": "", "final_answer": ""},
            {"raw_parse_success": False, "repaired_parse_success": False, "unsafe_repair": unsafe, "repair_method": method},
        )
    return (
        {"problem": "", "reasoning": "", "final_answer": ""},
        {"raw_parse_success": False, "repaired_parse_success": False, "unsafe_repair": unsafe, "repair_method": method},
    )


def run_iteration(
    subtype_root: Path,
    subtype: str,
    iteration: int,
    batch_size: int,
    model: str,
    rng: random.Random,
    strict_local_generation: bool,
) -> dict[str, Any]:
    generated: list[dict[str, Any]] = []
    validated: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    reject: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    reject_causes: Counter[str] = Counter()
    review_causes: Counter[str] = Counter()
    model_parse_failures = 0
    raw_parse_success = 0
    repaired_parse_success = 0
    unsafe_repair_count = 0

    for i in range(batch_size):
        params = random_params(rng, subtype)
        examples: list[tuple[str, str]] = []
        for _ in range(5):
            src = rng.randint(0, 255)
            dst = apply_rule(src, subtype, params)
            examples.append((to_bin8(src), to_bin8(dst)))
        q = rng.randint(0, 255)
        query_bin = to_bin8(q)
        if subtype in {"shift", "rotation", "xor", "and", "or", "not", "mixed"}:
            if subtype == "shift":
                generated_problem = build_shift_problem_train_style(examples, query_bin)
            elif subtype == "rotation":
                generated_problem = build_rotation_problem_train_style(examples, query_bin)
            elif subtype == "xor":
                generated_problem = build_xor_problem_train_style(examples, query_bin)
            elif subtype == "and":
                generated_problem = build_and_problem_train_style(examples, query_bin)
            elif subtype == "or":
                generated_problem = build_or_problem_train_style(examples, query_bin)
            elif subtype == "not":
                generated_problem = build_not_problem_train_style(examples, query_bin)
            else:
                generated_problem = build_mixed_problem_train_style(examples, query_bin)
            generated_reasoning = "The hidden transformation inferred from the examples is applied consistently to the query."
            generated_answer = f"\\boxed{{{to_bin8(apply_rule(q, subtype, params))}}}"
            parse_meta = {
                "raw_parse_success": True,
                "repaired_parse_success": False,
                "unsafe_repair": False,
                "repair_method": f"programmatic_{subtype}_prompt",
            }
        else:
            local_row, parse_meta = local_generate_sample(model, subtype, examples, query_bin, params, strict_local_generation)
            if strict_local_generation:
                generated_problem = local_row["problem"]
                generated_reasoning = local_row["reasoning"]
                generated_answer = local_row["final_answer"]
            else:
                generated_problem = local_row["problem"] or build_problem(subtype, examples, query_bin)
                generated_reasoning = local_row["reasoning"] or f"Subtype {subtype}: apply one consistent hidden rule."
                generated_answer = local_row["final_answer"] or to_bin8(apply_rule(q, subtype, params))
            if not local_row["problem"] or not local_row["reasoning"] or not local_row["final_answer"]:
                model_parse_failures += 1

        if parse_meta["raw_parse_success"]:
            raw_parse_success += 1
        if parse_meta["repaired_parse_success"]:
            repaired_parse_success += 1
        if parse_meta["unsafe_repair"]:
            unsafe_repair_count += 1
        row = {
            "id": f"binary_{subtype}_it{iteration:03d}_{i+1:04d}",
            "problem": generated_problem,
            "reasoning": generated_reasoning,
            "final_answer": generated_answer,
            "metadata": {
                "problem_type": "binary",
                "subgroup": subtype,
                "provider": "local",
                "model": model,
                "params": params,
                "parse_meta": parse_meta,
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

    # Adversarial sensitivity: inject controlled corruption and expect validator to catch it.
    adversarial_total = min(20, len(validated))
    detected = 0
    for idx in range(adversarial_total):
        bad = dict(validated[idx])
        bad["final_answer"] = force_wrong_answer(normalize_final_answer(str(bad["final_answer"])))
        bad_validation = validate_row(subtype, bad)
        if not (bad_validation["semantic_valid"] and bad_validation["format_valid"] and bad_validation["answer_correct"]):
            detected += 1

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
        "adversarial_detection_rate": round((detected / adversarial_total) if adversarial_total else 0.0, 6),
        "model_parse_failure_rate": round(model_parse_failures / batch_size, 6),
        "raw_parse_success_rate": round(raw_parse_success / batch_size, 6),
        "repaired_parse_success_rate": round(repaired_parse_success / batch_size, 6),
        "unsafe_repair_rate": round(unsafe_repair_count / batch_size, 6),
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
            w.writerow({"id": row["id"], "prompt": row["problem"], "answer": normalize_final_answer(row["final_answer"])})
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
        "min_adversarial_detection_rate": float(
            thresholds.get("min_adversarial_detection_rate", DEFAULT_THRESHOLDS["min_adversarial_detection_rate"])
        ),
    }

    state = "IN_PROGRESS"
    history: list[dict[str, Any]] = []
    consecutive_passes = 0
    rng = random.Random(seed + hash(subtype) % 10000)
    final_keep: list[dict[str, Any]] = []

    for it in range(1, max_iterations + 1):
        state = "CALIBRATING"
        result = run_iteration(st_root, subtype, it, batch_size, model, rng, strict_local_generation=True)
        metrics = result["metrics"]
        passed = (
            metrics["keep_rate"] >= thresholds["min_keep_rate"]
            and metrics["semantic_valid_rate"] >= thresholds["min_semantic_valid_rate"]
            and metrics["average_score"] >= thresholds["min_average_score"]
            and metrics["reject_rate"] <= thresholds["max_reject_rate"]
            and metrics["adversarial_detection_rate"] >= thresholds["min_adversarial_detection_rate"]
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
