#!/usr/bin/env python3
"""Binary/shift subtype loop: generate, validate, score, split, report."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FORBIDDEN_TERMS = ("xor", "and", "or", "not", "rotate", "rotation", "majority", "choice")


@dataclass
class Candidate:
    id: str
    problem: str
    reasoning: str
    final_answer: str
    metadata: dict[str, Any]


def to_bin8(value: int) -> str:
    return format(value & 0xFF, "08b")


def apply_shift(value: int, direction: str, amount: int) -> int:
    if direction == "left_shift":
        return (value << amount) & 0xFF
    if direction == "right_shift":
        return (value >> amount) & 0xFF
    raise ValueError(f"Unsupported direction: {direction}")


def parse_binary_from_problem(problem: str) -> str:
    marker = "Now, determine the output for:"
    if marker not in problem:
        return ""
    return problem.split(marker, 1)[1].strip()


def build_problem(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        "In Alice's Wonderland, a secret bit shift rule transforms 8-bit binary numbers.",
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)


def generate_one(rng: random.Random, idx: int) -> Candidate:
    direction = rng.choice(["left_shift", "right_shift"])
    amount = rng.randint(1, 3)

    examples: list[tuple[str, str]] = []
    for _ in range(5):
        value = rng.randint(0, 255)
        out = apply_shift(value, direction, amount)
        examples.append((to_bin8(value), to_bin8(out)))

    query_value = rng.randint(0, 255)
    query = to_bin8(query_value)
    answer = to_bin8(apply_shift(query_value, direction, amount))

    reasoning = (
        f"The hidden rule applies a {direction.replace('_', ' ')} by {amount} bit(s) "
        "to each 8-bit input. Applying that same shift to the query gives the final output."
    )
    return Candidate(
        id=f"binary_shift_{idx:06d}",
        problem=build_problem(examples, query),
        reasoning=reasoning,
        final_answer=answer,
        metadata={"operation": direction, "shift_amount": amount, "subtype": "binary/shift"},
    )


def validate(candidate: Candidate) -> dict[str, Any]:
    query = parse_binary_from_problem(candidate.problem)
    direction = candidate.metadata.get("operation")
    amount = int(candidate.metadata.get("shift_amount", 0))

    format_valid = len(candidate.final_answer) == 8 and set(candidate.final_answer).issubset({"0", "1"})
    semantic_valid = (
        direction in {"left_shift", "right_shift"}
        and 1 <= amount <= 3
        and len(query) == 8
        and set(query).issubset({"0", "1"})
        and all(term not in candidate.reasoning.lower() for term in FORBIDDEN_TERMS)
    )

    answer_correct = False
    if semantic_valid and format_valid:
        expected = to_bin8(apply_shift(int(query, 2), direction, amount))
        answer_correct = expected == candidate.final_answer

    return {
        "semantic_valid": semantic_valid,
        "format_valid": format_valid,
        "answer_correct": answer_correct,
        "errors": [
            reason
            for ok, reason in [
                (semantic_valid, "semantic_invalid"),
                (format_valid, "format_invalid"),
                (answer_correct, "answer_mismatch"),
            ]
            if not ok
        ],
    }


def score(validation: dict[str, Any], weights: dict[str, float]) -> float:
    value = 0.0
    value += weights["semantic_valid"] if validation["semantic_valid"] else 0.0
    value += weights["format_valid"] if validation["format_valid"] else 0.0
    value += weights["answer_correct"] if validation["answer_correct"] else 0.0
    return round(value, 6)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run binary/shift calibration loop.")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--subtype-root",
        default="data/subtypes/binary/shift",
        help="Root folder for binary/shift subtype artifacts.",
    )
    args = parser.parse_args()

    subtype_root = Path(args.subtype_root)
    thresholds = json.loads(
        (subtype_root / "config" / "quality_thresholds.json").read_text(encoding="utf-8")
    )["quality_gate"]
    weights = json.loads(
        (subtype_root / "config" / "quality_thresholds.json").read_text(encoding="utf-8")
    )["scoring_weights"]

    rng = random.Random(args.seed)

    generated_rows: list[dict[str, Any]] = []
    validated_rows: list[dict[str, Any]] = []
    keep_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    reject_rows: list[dict[str, Any]] = []

    for idx in range(1, args.batch_size + 1):
        sample = generate_one(rng, idx)
        raw = {
            "id": sample.id,
            "subtype": "binary/shift",
            "problem": sample.problem,
            "reasoning": sample.reasoning,
            "final_answer": sample.final_answer,
            "metadata": sample.metadata,
        }
        generated_rows.append(raw)

        validation = validate(sample)
        row_score = score(validation, weights)
        validated = {**raw, "validation": validation, "score": row_score}
        validated_rows.append(validated)

        if validation["semantic_valid"] and validation["format_valid"] and validation["answer_correct"]:
            keep_rows.append(validated)
        elif validation["semantic_valid"]:
            review_rows.append(validated)
        else:
            reject_rows.append(validated)

    write_jsonl(subtype_root / "generated" / "candidates.jsonl", generated_rows)
    write_jsonl(subtype_root / "validated" / "validated.jsonl", validated_rows)
    write_jsonl(subtype_root / "reviewed" / "keep.jsonl", keep_rows)
    write_jsonl(subtype_root / "reviewed" / "review.jsonl", review_rows)
    write_jsonl(subtype_root / "rejected" / "reject.jsonl", reject_rows)
    write_jsonl(subtype_root / "final" / "train_ready.jsonl", keep_rows)

    keep_rate = len(keep_rows) / args.batch_size if args.batch_size else 0.0
    reject_rate = len(reject_rows) / args.batch_size if args.batch_size else 0.0
    semantic_valid_rate = (
        sum(1 for row in validated_rows if row["validation"]["semantic_valid"]) / args.batch_size
        if args.batch_size
        else 0.0
    )
    avg_score = (
        sum(float(row["score"]) for row in validated_rows) / args.batch_size if args.batch_size else 0.0
    )

    quality_gate_passed = (
        keep_rate >= float(thresholds["min_keep_rate"])
        and reject_rate <= float(thresholds["max_reject_rate"])
        and semantic_valid_rate >= float(thresholds["min_semantic_valid_rate"])
        and avg_score >= float(thresholds["min_average_score"])
    )

    report = {
        "meta": {
            "subtype": "binary/shift",
            "batch_size": args.batch_size,
            "seed": args.seed,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "metrics": {
            "keep_rate": round(keep_rate, 6),
            "reject_rate": round(reject_rate, 6),
            "semantic_valid_rate": round(semantic_valid_rate, 6),
            "average_score": round(avg_score, 6),
            "keep_count": len(keep_rows),
            "review_count": len(review_rows),
            "reject_count": len(reject_rows),
        },
        "quality_gate": {
            "thresholds": thresholds,
            "passed": quality_gate_passed,
        },
    }

    report_path = subtype_root / "reports" / "quality_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report["metrics"], ensure_ascii=False))
    print(f"Quality gate passed: {quality_gate_passed}")
    if not quality_gate_passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
