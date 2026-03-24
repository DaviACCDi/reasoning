#!/usr/bin/env python3
"""Consolidate final binary subtype datasets into a single balanced export."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

SUBTYPES = ("shift", "rotation", "xor", "and", "or", "not", "mixed")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    root = Path("data/subtypes/binary")
    out_dir = Path("data/final/binary")
    out_dir.mkdir(parents=True, exist_ok=True)

    consolidated: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    quality: dict[str, dict] = {}
    keep_reject: dict[str, dict[str, float]] = {}

    for subtype in SUBTYPES:
        csv_path = root / subtype / "final" / "train_ready.csv"
        rows = read_csv_rows(csv_path)
        counts[subtype] = len(rows)
        for row in rows:
            row["subtype"] = f"binary/{subtype}"
            consolidated.append(row)

        report_path = root / subtype / "reports" / "final_quality_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        metrics = report.get("metrics", {})
        quality[subtype] = metrics
        keep_reject[subtype] = {
            "keep_rate": float(metrics.get("keep_rate", 0.0)),
            "reject_rate": float(metrics.get("reject_rate", 0.0)),
        }

    consolidated_sorted = sorted(consolidated, key=lambda r: (r["subtype"], r["id"]))

    csv_out = out_dir / "binary_train_ready.csv"
    with csv_out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "prompt", "answer"])
        writer.writeheader()
        for row in consolidated_sorted:
            writer.writerow({"id": row["id"], "prompt": row["prompt"], "answer": row["answer"]})

    jsonl_out = out_dir / "binary_train_ready.jsonl"
    write_jsonl(jsonl_out, [{"id": r["id"], "prompt": r["prompt"], "answer": r["answer"]} for r in consolidated_sorted])

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "domain": "binary",
        "expected_per_subtype": 1000,
        "subtype_counts": counts,
        "total_rows": len(consolidated_sorted),
        "distribution_balanced": len(set(counts.values())) == 1,
        "quality": {
            "per_subtype_keep_reject": keep_reject,
            "per_subtype_metrics": quality,
        },
    }
    (out_dir / "binary_distribution_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    freeze = {
        "generated_at": summary["generated_at"],
        "frozen_subtypes": [f"binary/{s}" for s in SUBTYPES],
        "frozen_files": {
            s: {
                "prompt_final": str((root / s / "config" / "prompt_final.md").as_posix()),
                "quality_thresholds": str((root / s / "config" / "quality_thresholds.json").as_posix()),
                "final_quality_report": str((root / s / "reports" / "final_quality_report.json").as_posix()),
            }
            for s in SUBTYPES
        },
    }
    (out_dir / "binary_freeze_manifest.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")

    pr_manifest = {
        "generated_at": summary["generated_at"],
        "repo": "https://github.com/DaviACCDi/reasoning",
        "subtype_pr_links": {
            s: f"https://github.com/DaviACCDi/reasoning/pull/new/feature/binary-{s}" for s in SUBTYPES
        },
    }
    (out_dir / "binary_pr_consolidation.json").write_text(json.dumps(pr_manifest, indent=2), encoding="utf-8")

    print(f"Consolidated rows: {len(consolidated_sorted)}")
    print(f"CSV:   {csv_out}")
    print(f"JSONL: {jsonl_out}")


if __name__ == "__main__":
    main()
