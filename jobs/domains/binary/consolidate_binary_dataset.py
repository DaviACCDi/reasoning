#!/usr/bin/env python3
"""Consolidate approved binary records into final train-ready dataset."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate approved binary records.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--export-csv", action="store_true")
    parser.add_argument("--export-jsonl", action="store_true")
    parser.add_argument("--deliverables-root", default="deliverables/binary")
    args = parser.parse_args()

    run_root = Path(args.output_root) / args.run_id
    approved_path = run_root / "approved" / "approved.jsonl"
    final_dir = run_root / "final"
    reports_dir = run_root / "reports"
    final_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    approved = read_jsonl(approved_path)
    final_rows = [{"id": r["id"], "prompt": r["prompt"], "answer": r["answer"]} for r in approved]
    final_rows.sort(key=lambda x: x["id"])

    if args.export_jsonl or not args.export_csv:
        write_jsonl(final_dir / "binary_train_ready.jsonl", final_rows)
    if args.export_csv or not args.export_jsonl:
        csv_path = final_dir / "binary_train_ready.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "prompt", "answer"])
            writer.writeheader()
            writer.writerows(final_rows)

    summary = {
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "final_count": len(final_rows),
        "final_paths": {
            "csv": str((final_dir / "binary_train_ready.csv").as_posix()),
            "jsonl": str((final_dir / "binary_train_ready.jsonl").as_posix()),
        },
    }
    (reports_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    deliver_latest = Path(args.deliverables_root) / "latest"
    deliver_latest.mkdir(parents=True, exist_ok=True)
    if (final_dir / "binary_train_ready.csv").exists():
        (deliver_latest / "binary_train_ready.csv").write_text(
            (final_dir / "binary_train_ready.csv").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    if (final_dir / "binary_train_ready.jsonl").exists():
        (deliver_latest / "binary_train_ready.jsonl").write_text(
            (final_dir / "binary_train_ready.jsonl").read_text(encoding="utf-8"),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
