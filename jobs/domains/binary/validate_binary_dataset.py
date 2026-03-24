#!/usr/bin/env python3
"""Validate binary domain candidates and split approved/rejected."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from common import SUBTYPES, apply_rule, dump_json, load_json, to_bin8, write_jsonl


def validate_row(row: dict[str, Any]) -> tuple[bool, list[str], float]:
    errors: list[str] = []
    subtype = row["subtype"]
    prompt = str(row["prompt"])
    answer = str(row["answer"])
    params = row["metadata"]["params"]
    query = row["metadata"]["query"]
    examples = row["metadata"]["examples"]

    if subtype not in SUBTYPES:
        errors.append("invalid_subtype")
    if "Now, determine the output for:" not in prompt:
        errors.append("missing_query_marker")
    if len(answer) != 8 or set(answer) - {"0", "1"}:
        errors.append("invalid_answer_format")
    if len(query) != 8 or set(query) - {"0", "1"}:
        errors.append("invalid_query_format")
    if not isinstance(examples, list) or len(examples) < 3:
        errors.append("insufficient_examples")
    else:
        for src, dst in examples:
            if len(src) != 8 or len(dst) != 8 or (set(src) - {"0", "1"}) or (set(dst) - {"0", "1"}):
                errors.append("invalid_example_format")
                break
            exp = to_bin8(apply_rule(int(src, 2), subtype, params))
            if exp != dst:
                errors.append("example_rule_mismatch")
                break

    expected = to_bin8(apply_rule(int(query, 2), subtype, params)) if "invalid_query_format" not in errors else ""
    if expected and expected != answer:
        errors.append("answer_mismatch")

    ok = len(errors) == 0
    score = 1.0 if ok else max(0.0, 1.0 - 0.2 * len(errors))
    return ok, errors, round(score, 6)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            import json

            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate binary domain generated records.")
    parser.add_argument("--thresholds-file", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_root = Path(args.output_root) / args.run_id
    generated_path = run_root / "generated" / "all_candidates.jsonl"
    validated_dir = run_root / "validated"
    approved_dir = run_root / "approved"
    rejected_dir = run_root / "rejected"
    reports_dir = run_root / "reports"
    validated_dir.mkdir(parents=True, exist_ok=True)
    approved_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    thresholds = load_json(Path(args.thresholds_file))
    min_score = float(thresholds["min_score_for_approval"])
    max_duplicate_rate = float(thresholds["max_duplicate_prompt_rate"])

    rows = read_jsonl(generated_path)
    validated_rows: list[dict[str, Any]] = []
    approved_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    reject_causes: Counter[str] = Counter()
    subtype_counts: Counter[str] = Counter()
    subtype_approved: Counter[str] = Counter()
    level_counts: Counter[str] = Counter()
    prompt_counter: Counter[str] = Counter()

    for row in rows:
        subtype_counts[row["subtype"]] += 1
        if row["subtype"] == "mixed":
            level_counts[str(row.get("level", "L1"))] += 1
        prompt_counter[row["prompt"]] += 1

        ok, errors, score = validate_row(row)
        out = {**row, "validation": {"approved": ok and score >= min_score, "errors": errors, "score": score}}
        validated_rows.append(out)
        if out["validation"]["approved"]:
            approved_rows.append(out)
            subtype_approved[row["subtype"]] += 1
        else:
            rejected_rows.append(out)
            for e in errors:
                reject_causes[e] += 1

    duplicate_prompts = sum(1 for _, c in prompt_counter.items() if c > 1)
    duplicate_rate = duplicate_prompts / len(prompt_counter) if prompt_counter else 0.0
    distribution_expected = load_json(Path("config/domains/binary/distribution.default.json"))["subtype_distribution"]
    distribution_actual = {k: (subtype_approved[k] / max(1, len(approved_rows))) for k in SUBTYPES}

    write_jsonl(validated_dir / "all_validated.jsonl", validated_rows)
    write_jsonl(approved_dir / "approved.jsonl", approved_rows)
    write_jsonl(rejected_dir / "rejected.jsonl", rejected_rows)

    dump_json(
        reports_dir / "quality_report.json",
        {
            "run_id": args.run_id,
            "approved_count": len(approved_rows),
            "rejected_count": len(rejected_rows),
            "approval_rate": round(len(approved_rows) / max(1, len(rows)), 6),
            "avg_score": round(sum(r["validation"]["score"] for r in validated_rows) / max(1, len(rows)), 6),
            "reject_causes": dict(reject_causes),
            "duplicate_prompt_rate": round(duplicate_rate, 6),
            "duplicate_prompt_rate_ok": duplicate_rate <= max_duplicate_rate,
        },
    )
    dump_json(
        reports_dir / "distribution_report.json",
        {
            "run_id": args.run_id,
            "counts_generated": dict(subtype_counts),
            "counts_approved": dict(subtype_approved),
            "expected_distribution": distribution_expected,
            "actual_distribution_approved": distribution_actual,
            "mixed_level_distribution_generated": dict(level_counts),
        },
    )
    dump_json(
        reports_dir / "rejection_report.json",
        {
            "run_id": args.run_id,
            "rejected_count": len(rejected_rows),
            "causes": dict(reject_causes),
        },
    )


if __name__ == "__main__":
    main()
