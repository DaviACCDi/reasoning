#!/usr/bin/env python3
"""Orchestrate text/substitution variant calibration (programmatic train-style generation)."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Priority order: train anchor first, then synthetic families, mixed last.
SUBTYPES = ("custom_mapping", "caesar_shift", "reverse_alphabet", "number_mapping", "mixed")
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

TRAIN_HEADER = "In Alice's Wonderland, secret encryption rules are used on text. Here are some examples:"

WORD_BANK = [
    "alice",
    "queen",
    "dragon",
    "castle",
    "valley",
    "mirror",
    "palace",
    "mountain",
    "hatter",
    "wizard",
    "secret",
    "bird",
    "reads",
    "follows",
    "discovers",
    "creates",
    "magical",
    "door",
    "princess",
    "mysterious",
    "near",
    "inside",
    "imagines",
    "chases",
    "draws",
    "under",
    "wise",
    "student",
    "golden",
    "ancient",
    "book",
    "cat",
    "mouse",
    "dreams",
    "watches",
    "wonderland",
]

PROMPTS_V1: dict[str, str] = {
    "custom_mapping": "Monoalphabetic substitution learned only from cipher -> plain examples; decrypt final line.",
    "caesar_shift": "Uniform Caesar shift on a-z; same train envelope; never name Caesar in the prompt.",
    "reverse_alphabet": "Atbash-style reverse alphabet mapping on a-z; train envelope only.",
    "number_mapping": "Letters encoded as 1-26 with hyphen per word; decrypt query to lowercase words.",
    "mixed": "Two-step pipeline (Caesar then reverse or reverse then Caesar); verify full pipeline on all pairs.",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_final_answer(text: str) -> str:
    t = str(text).strip()
    if t.startswith("\\boxed{") and t.endswith("}"):
        return t[8:-1].strip()
    return t


def parse_arrow_pairs(problem: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for ln in problem.splitlines():
        if " -> " not in ln:
            continue
        left, right = ln.split(" -> ", 1)
        left, right = left.strip(), right.strip()
        if not left or not right:
            continue
        pairs.append((left, right))
    return pairs


def extract_query_cipher(problem: str) -> str:
    mark = "Now, decrypt the following text:"
    if mark not in problem:
        return ""
    return problem.split(mark, 1)[1].strip()


def random_phrase(rng: random.Random, min_words: int = 3, max_words: int = 6) -> str:
    n = rng.randint(min_words, max_words)
    return " ".join(rng.choice(WORD_BANK) for _ in range(n))


def build_problem(example_pairs: list[tuple[str, str]], cipher_query: str) -> str:
    lines = [TRAIN_HEADER, ""]
    for c, p in example_pairs:
        lines.append(f"{c} -> {p}")
    lines.append("")
    lines.append(f"Now, decrypt the following text: {cipher_query}")
    return "\n".join(lines)


# --- custom_mapping -----------------------------------------------------------------
def random_bijection_forward(rng: random.Random) -> dict[str, str]:
    letters = [chr(97 + i) for i in range(26)]
    perm = letters[:]
    rng.shuffle(perm)
    return dict(zip(letters, perm))


def apply_forward_map(text: str, forward: dict[str, str]) -> str:
    out: list[str] = []
    for ch in text:
        if ch == " ":
            out.append(" ")
        else:
            out.append(forward[ch])
    return "".join(out)


def invert_map(m: dict[str, str]) -> dict[str, str]:
    return {v: k for k, v in m.items()}


# --- caesar -------------------------------------------------------------------------
def enc_caesar_char(c: str, shift: int) -> str:
    return chr((ord(c) - 97 + shift) % 26 + 97)


def dec_caesar_char(c: str, shift: int) -> str:
    return chr((ord(c) - 97 - shift) % 26 + 97)


def enc_caesar_text(text: str, shift: int) -> str:
    return "".join(" " if ch == " " else enc_caesar_char(ch, shift) for ch in text)


def dec_caesar_text(text: str, shift: int) -> str:
    return "".join(" " if ch == " " else dec_caesar_char(ch, shift) for ch in text)


def infer_caesar_shift(pairs: list[tuple[str, str]]) -> int | None:
    shifts: set[int] = set()
    for ciph, plain in pairs:
        if len(ciph) != len(plain):
            return None
        for i in range(len(ciph)):
            cc, pc = ciph[i], plain[i]
            if cc == " ":
                if pc != " ":
                    return None
                continue
            if not (cc.islower() and pc.islower()):
                return None
            shifts.add((ord(cc) - ord(pc)) % 26)
    if len(shifts) != 1:
        return None
    return shifts.pop()


# --- reverse ------------------------------------------------------------------------
def enc_rev_char(c: str) -> str:
    return chr(219 - ord(c))


def enc_rev_text(text: str) -> str:
    return "".join(" " if ch == " " else enc_rev_char(ch) for ch in text)


def dec_rev_text(text: str) -> str:
    return enc_rev_text(text)


# --- number mapping -----------------------------------------------------------------
def encode_number_phrase(phrase: str) -> str:
    words = phrase.split()
    return " ".join("-".join(str(ord(c) - 96) for c in w) for w in words)


def decode_number_token(group: str) -> str | None:
    parts = group.split("-")
    out: list[str] = []
    for p in parts:
        if not p.isdigit():
            return None
        n = int(p)
        if n < 1 or n > 26:
            return None
        out.append(chr(96 + n))
    return "".join(out)


def decode_number_cipher(cipher: str) -> str | None:
    tokens = cipher.split()
    words: list[str] = []
    for t in tokens:
        w = decode_number_token(t)
        if w is None:
            return None
        words.append(w)
    return " ".join(words)


# --- mixed pipeline -----------------------------------------------------------------
def enc_char_step(c: str, step: dict[str, Any]) -> str:
    t = step["type"]
    if t == "caesar":
        return enc_caesar_char(c, int(step["shift"]))
    if t == "reverse":
        return enc_rev_char(c)
    if t == "custom":
        return step["forward"][c]
    raise ValueError(t)


def dec_char_step(c: str, step: dict[str, Any]) -> str:
    t = step["type"]
    if t == "caesar":
        return dec_caesar_char(c, int(step["shift"]))
    if t == "reverse":
        return enc_rev_char(c)
    if t == "custom":
        return step["inverse"][c]
    raise ValueError(t)


def enc_text_pipeline(text: str, pipeline: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for ch in text:
        if ch == " ":
            out.append(" ")
            continue
        x = ch
        for st in pipeline:
            x = enc_char_step(x, st)
        out.append(x)
    return "".join(out)


def dec_text_pipeline(text: str, pipeline: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for ch in text:
        if ch == " ":
            out.append(" ")
            continue
        x = ch
        for st in reversed(pipeline):
            x = dec_char_step(x, st)
        out.append(x)
    return "".join(out)


def random_mixed_pipeline(rng: random.Random) -> list[dict[str, Any]]:
    shift = rng.randint(1, 25)
    if rng.random() < 0.5:
        return [{"type": "caesar", "shift": shift}, {"type": "reverse"}]
    return [{"type": "reverse"}, {"type": "caesar", "shift": shift}]


def random_params(rng: random.Random, subtype: str) -> dict[str, Any]:
    if subtype == "custom_mapping":
        fwd = random_bijection_forward(rng)
        return {"operation": "custom_mapping", "forward": fwd, "inverse": invert_map(fwd)}
    if subtype == "caesar_shift":
        return {"operation": "caesar_shift", "shift": rng.randint(1, 25)}
    if subtype == "reverse_alphabet":
        return {"operation": "reverse_alphabet"}
    if subtype == "number_mapping":
        return {"operation": "number_mapping"}
    if subtype == "mixed":
        pipe = random_mixed_pipeline(rng)
        return {"operation": "mixed", "pipeline": pipe}
    raise ValueError(subtype)


def encrypt_plain(subtype: str, plain: str, params: dict[str, Any]) -> str:
    if subtype == "custom_mapping":
        return apply_forward_map(plain, params["forward"])
    if subtype == "caesar_shift":
        return enc_caesar_text(plain, int(params["shift"]))
    if subtype == "reverse_alphabet":
        return enc_rev_text(plain)
    if subtype == "number_mapping":
        return encode_number_phrase(plain)
    if subtype == "mixed":
        return enc_text_pipeline(plain, params["pipeline"])
    raise ValueError(subtype)


def decrypt_answer(subtype: str, cipher: str, params: dict[str, Any]) -> str | None:
    if subtype == "custom_mapping":
        return apply_forward_map(cipher, params["inverse"])
    if subtype == "caesar_shift":
        return dec_caesar_text(cipher, int(params["shift"]))
    if subtype == "reverse_alphabet":
        return dec_rev_text(cipher)
    if subtype == "number_mapping":
        return decode_number_cipher(cipher)
    if subtype == "mixed":
        return dec_text_pipeline(cipher, params["pipeline"])
    return None


def validate_row(subtype: str, row: dict[str, Any]) -> dict[str, Any]:
    validation: dict[str, Any] = {
        "semantic_valid": True,
        "format_valid": True,
        "answer_correct": True,
        "errors": [],
    }
    problem = str(row["problem"])
    normalized_answer = normalize_final_answer(str(row["final_answer"]))

    if TRAIN_HEADER not in problem:
        validation["format_valid"] = False
        validation["errors"].append("missing_train_header")
    if "Now, decrypt the following text:" not in problem:
        validation["format_valid"] = False
        validation["errors"].append("missing_decrypt_marker")

    example_pairs = [p for p in parse_arrow_pairs(problem) if p[0] and p[1]]
    if len(example_pairs) < 3:
        validation["semantic_valid"] = False
        validation["errors"].append("insufficient_examples")

    query_cipher = extract_query_cipher(problem)
    if not query_cipher:
        validation["semantic_valid"] = False
        validation["errors"].append("missing_query_cipher")

    params = row["metadata"]["params"]

    if validation["semantic_valid"] and example_pairs:
        if subtype in ("custom_mapping", "caesar_shift", "reverse_alphabet"):
            for ciph, plain in example_pairs:
                if len(ciph) != len(plain):
                    validation["semantic_valid"] = False
                    validation["errors"].append("example_length_mismatch")
                    break
                for i in range(len(ciph)):
                    cc, pc = ciph[i], plain[i]
                    if cc == " ":
                        if pc != " ":
                            validation["semantic_valid"] = False
                            validation["errors"].append("space_mismatch")
                            break
                    elif not (cc.islower() and pc.islower()):
                        validation["semantic_valid"] = False
                        validation["errors"].append("non_lower_alpha")
                        break
                if not validation["semantic_valid"]:
                    break
            if validation["semantic_valid"]:
                if subtype == "caesar_shift":
                    sh = infer_caesar_shift(example_pairs)
                    if sh is None:
                        validation["semantic_valid"] = False
                        validation["errors"].append("example_rule_mismatch")
                    elif sh != int(params["shift"]):
                        validation["semantic_valid"] = False
                        validation["errors"].append("example_rule_mismatch")
                elif subtype == "reverse_alphabet":
                    for ciph, plain in example_pairs:
                        if dec_rev_text(ciph) != plain:
                            validation["semantic_valid"] = False
                            validation["errors"].append("example_rule_mismatch")
                            break
                elif subtype == "custom_mapping":
                    inv: dict[str, str] = {}
                    ok = True
                    for ciph, plain in example_pairs:
                        for i in range(len(ciph)):
                            cc, pc = ciph[i], plain[i]
                            if cc == " ":
                                continue
                            if cc in inv and inv[cc] != pc:
                                ok = False
                                break
                            inv[cc] = pc
                        if not ok:
                            break
                    if not ok:
                        validation["semantic_valid"] = False
                        validation["errors"].append("example_rule_mismatch")
                    elif len(inv.values()) != len(set(inv.values())):
                        validation["semantic_valid"] = False
                        validation["errors"].append("mapping_not_injective")
                    else:
                        for ciph, plain in example_pairs:
                            dec = "".join(
                                " " if ciph[i] == " " else inv[ciph[i]] for i in range(len(ciph))
                            )
                            if dec != plain:
                                validation["semantic_valid"] = False
                                validation["errors"].append("example_rule_mismatch")
                                break

        elif subtype == "number_mapping":
            for ciph, plain in example_pairs:
                got = decode_number_cipher(ciph)
                if got is None or got != plain:
                    validation["semantic_valid"] = False
                    validation["errors"].append("example_rule_mismatch")
                    break

        elif subtype == "mixed":
            pipe = params["pipeline"]
            for ciph, plain in example_pairs:
                if dec_text_pipeline(ciph, pipe) != plain:
                    validation["semantic_valid"] = False
                    validation["errors"].append("example_rule_mismatch")
                    break

    if validation["semantic_valid"] and query_cipher:
        expected = decrypt_answer(subtype, query_cipher, params)
        if expected is None:
            validation["answer_correct"] = False
            validation["errors"].append("answer_unverifiable")
        elif expected != normalized_answer:
            validation["answer_correct"] = False
            validation["errors"].append("answer_mismatch")

    if not validation["format_valid"]:
        validation["semantic_valid"] = False

    return validation


def score_row(validation: dict[str, Any]) -> float:
    return round(
        (0.50 if validation["semantic_valid"] else 0.0)
        + (0.30 if validation["format_valid"] else 0.0)
        + (0.20 if validation["answer_correct"] else 0.0),
        6,
    )


def force_wrong_answer(text: str) -> str:
    t = text.strip()
    if not t:
        return "wrong"
    parts = t.split()
    if not parts[0]:
        return "wrong"
    w = list(parts[0])
    w[0] = "z" if w[0] != "z" else "a"
    parts[0] = "".join(w)
    return " ".join(parts)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ensure_subtype_layout(root: Path, variant: str) -> Path:
    st_root = root / "text" / "substitution" / variant
    for folder in SUBTYPE_FOLDERS:
        (st_root / folder).mkdir(parents=True, exist_ok=True)
    thresholds_path = st_root / "config" / "quality_thresholds.json"
    if not thresholds_path.exists():
        thresholds_path.write_text(
            json.dumps(
                {
                    "subtype": f"text/substitution/{variant}",
                    "generation_provider": "local",
                    "generation_model": "llama3.1:8b",
                    **DEFAULT_THRESHOLDS,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    prompt_v1 = st_root / "config" / "prompt_v1.md"
    if not prompt_v1.exists():
        prompt_v1.write_text(
            f"# {variant}\n\n{PROMPTS_V1.get(variant, '')}\n",
            encoding="utf-8",
        )
    return st_root


def run_iteration(
    subtype_root: Path,
    subtype: str,
    iteration: int,
    batch_size: int,
    model: str,
    rng: random.Random,
) -> dict[str, Any]:
    generated: list[dict[str, Any]] = []
    validated: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    reject: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    reject_causes: Counter[str] = Counter()
    review_causes: Counter[str] = Counter()
    model_parse_failures = 0
    raw_parse_success = batch_size
    repaired_parse_success = 0
    unsafe_repair_count = 0

    for i in range(batch_size):
        params = random_params(rng, subtype)
        example_count = rng.randint(8, 10)
        example_pairs: list[tuple[str, str]] = []
        for _ in range(example_count):
            plain = random_phrase(rng)
            ciph = encrypt_plain(subtype, plain, params)
            example_pairs.append((ciph, plain))

        plain_query = random_phrase(rng, 2, 4)
        cipher_query = encrypt_plain(subtype, plain_query, params)
        generated_problem = build_problem(example_pairs, cipher_query)
        generated_reasoning = "The ciphertext-to-plaintext mapping implied by the examples is applied to the final line."
        generated_answer = plain_query

        parse_meta = {
            "raw_parse_success": True,
            "repaired_parse_success": False,
            "unsafe_repair": False,
            "repair_method": f"programmatic_{subtype}",
        }

        row = {
            "id": f"text_subst_{subtype}_it{iteration:03d}_{i+1:04d}",
            "problem": generated_problem,
            "reasoning": generated_reasoning,
            "final_answer": generated_answer,
            "metadata": {
                "problem_type": "text",
                "subgroup": f"substitution/{subtype}",
                "provider": "local",
                "model": model,
                "params": params,
            },
        }
        generated.append(row)
        validation = validate_row(subtype, row)
        scored = {**row, "validation": validation, "score": score_row(validation)}
        validated.append(scored)
        if validation["semantic_valid"] and validation["format_valid"] and validation["answer_correct"] and scored["score"] >= 0.99:
            keep.append(scored)
        elif validation["semantic_valid"]:
            review.append(scored)
            for cause in validation["errors"]:
                review_causes[cause] += 1
        else:
            reject.append(scored)
            for cause in validation["errors"]:
                reject_causes[cause] += 1

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
            w.writerow(
                {
                    "id": row["id"],
                    "prompt": row["problem"],
                    "answer": normalize_final_answer(row["final_answer"]),
                }
            )
    write_jsonl(subtype_root / "reviewed" / "keep.jsonl", keep_rows)


def create_pr_summary(subtype_root: Path, variant: str, final_report: dict[str, Any]) -> None:
    summary = {
        "subtype": f"text/substitution/{variant}",
        "branch": f"feature/text-substitution-{variant.replace('_', '-')}",
        "state": "READY_FOR_PR",
        "strategy": "Programmatic train-style prompts; local model calibration to follow in later iterations.",
        "metrics": final_report["metrics"],
        "artifacts": [
            "config/prompt_v1.md",
            "final/train_ready.jsonl",
            "final/train_ready.csv",
            "reports/final_quality_report.json",
        ],
        "generated_at": utc_now(),
    }
    (subtype_root / "reports" / "merge_request_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_subtype(root: Path, variant: str, model: str, batch_size: int, max_iterations: int, seed: int) -> dict[str, Any]:
    st_root = ensure_subtype_layout(root, variant)
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
    rng = random.Random(seed + hash(variant) % 10000)
    final_keep: list[dict[str, Any]] = []

    for it in range(1, max_iterations + 1):
        state = "CALIBRATING"
        result = run_iteration(st_root, variant, it, batch_size, model, rng)
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

        pv = st_root / "config" / f"prompt_v{it + 1}.md"
        pv.write_text(
            f"{PROMPTS_V1[variant]}\n\nCalibration note: iteration {it} => "
            f"keep={metrics['keep_rate']} reject={metrics['reject_rate']} score={metrics['average_score']}\n",
            encoding="utf-8",
        )

    if state == "STABLE":
        state = "READY_FOR_PR"
        export_final(st_root, final_keep)
        final_metrics = history[-1]["metrics"]
        (st_root / "reports" / "final_quality_report.json").write_text(
            json.dumps({"variant": variant, "metrics": final_metrics, "generated_at": utc_now()}, indent=2),
            encoding="utf-8",
        )
        create_pr_summary(st_root, variant, {"metrics": final_metrics})

    return {
        "subtype": f"text/substitution/{variant}",
        "state": state,
        "history": history,
        "metrics": history[-1]["metrics"] if history else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestrate text/substitution variant calibration.")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--provider", default="local")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--subtypes", default="all", help="Comma-separated variants or 'all'")
    parser.add_argument("--root", default="data/subtypes")
    args = parser.parse_args()

    if args.provider != "local":
        raise ValueError("This orchestrator supports only local provider metadata for now.")

    chosen = SUBTYPES if args.subtypes == "all" else tuple(x.strip() for x in args.subtypes.split(",") if x.strip())
    root = Path(args.root)
    shared_reports = root / "text" / "substitution" / "_shared" / "reports"
    shared_reports.mkdir(parents=True, exist_ok=True)

    overall: dict[str, Any] = {
        "domain": "text/substitution",
        "provider": args.provider,
        "model": args.model,
        "started_at": utc_now(),
        "states": list(STATES),
        "subtypes": {},
    }

    for variant in chosen:
        overall["subtypes"][variant] = run_subtype(root, variant, args.model, args.batch_size, args.max_iterations, args.seed)

    overall["finished_at"] = utc_now()
    out_path = shared_reports / "orchestrator_report.json"
    out_path.write_text(json.dumps(overall, indent=2), encoding="utf-8")
    print(f"Orchestrator report: {out_path}")
    for k, v in overall["subtypes"].items():
        print(f"{k}: {v['state']}")


if __name__ == "__main__":
    main()
