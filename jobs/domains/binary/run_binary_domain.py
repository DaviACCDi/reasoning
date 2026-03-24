#!/usr/bin/env python3
"""Main runner for binary domain local dataset production."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_step(step_name: str, cmd: list[str]) -> None:
    print(f"[binary-domain] {step_name}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"Step failed: {step_name} (exit={proc.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full binary domain dataset pipeline.")
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--distribution-file", default="config/domains/binary/distribution.default.json")
    parser.add_argument("--mixed-config", default="config/domains/binary/mixed_level_mix.json")
    parser.add_argument("--output-root", default="data/domains/binary/runs")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--thresholds-file", default="config/domains/binary/quality_thresholds.json")
    parser.add_argument("--export-csv", action="store_true")
    parser.add_argument("--export-jsonl", action="store_true")
    args = parser.parse_args()

    run_root = Path(args.output_root) / args.run_id
    for folder in ("generated", "validated", "approved", "rejected", "final", "reports"):
        (run_root / folder).mkdir(parents=True, exist_ok=True)

    py = sys.executable
    run_step(
        "generate",
        [
            py,
            "jobs/domains/binary/generate_binary_candidates.py",
            "--total",
            str(args.total),
            "--distribution-file",
            args.distribution_file,
            "--mixed-config",
            args.mixed_config,
            "--output-root",
            args.output_root,
            "--run-id",
            args.run_id,
            "--seed",
            str(args.seed),
            "--model",
            args.model,
        ],
    )
    run_step(
        "validate",
        [
            py,
            "jobs/domains/binary/validate_binary_dataset.py",
            "--thresholds-file",
            args.thresholds_file,
            "--output-root",
            args.output_root,
            "--run-id",
            args.run_id,
        ],
    )
    consolidate_cmd = [
        py,
        "jobs/domains/binary/consolidate_binary_dataset.py",
        "--output-root",
        args.output_root,
        "--run-id",
        args.run_id,
    ]
    if args.export_csv:
        consolidate_cmd.append("--export-csv")
    if args.export_jsonl:
        consolidate_cmd.append("--export-jsonl")
    run_step("consolidate", consolidate_cmd)

    print(f"[binary-domain] completed run_id={args.run_id}")
    print(f"[binary-domain] final path: {run_root / 'final'}")
    print(f"[binary-domain] reports path: {run_root / 'reports'}")


if __name__ == "__main__":
    main()
