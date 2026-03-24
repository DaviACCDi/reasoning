#!/usr/bin/env python3
"""Generate binary domain candidates using validated architecture."""

from __future__ import annotations

import argparse
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

from common import OPS, SUBTYPES, apply_rule, build_train_style_prompt, dump_json, load_json, random_params, to_bin8, write_jsonl


def compute_counts(total: int, dist: dict[str, float]) -> dict[str, int]:
    raw = {k: total * float(dist[k]) for k in SUBTYPES}
    base = {k: int(math.floor(v)) for k, v in raw.items()}
    remaining = total - sum(base.values())
    frac_sorted = sorted(SUBTYPES, key=lambda k: raw[k] - base[k], reverse=True)
    for i in range(remaining):
        base[frac_sorted[i % len(frac_sorted)]] += 1
    return base


def weighted_level_choice(rng: random.Random, level_mix: dict[str, float]) -> tuple[str, int]:
    levels = [("L1", 2), ("L2", 3), ("L3", 4)]
    weights = [float(level_mix.get(name, 0.0)) for name, _ in levels]
    total = sum(weights)
    pick = rng.random() * (total if total > 0 else 1.0)
    acc = 0.0
    for (name, size), w in zip(levels, weights):
        acc += w
        if pick <= acc:
            return name, size
    return "L1", 2


def build_mixed_params(
    rng: random.Random,
    used_signatures: Counter[str],
    level_mix: dict[str, float],
    coverage_cfg: dict[str, Any],
) -> dict[str, Any]:
    allowed = list(coverage_cfg.get("allowed_operations", list(OPS)))
    max_same = int(coverage_cfg.get("max_identical_operation_steps", 2))
    max_reuse = int(coverage_cfg.get("max_pipeline_reuse", 12))
    for _ in range(100):
        level, n_ops = weighted_level_choice(rng, level_mix)
        ops: list[str] = []
        while len(ops) < n_ops:
            op = rng.choice(allowed)
            if len(ops) >= max_same - 1 and all(o == op for o in ops[-(max_same - 1) :]):
                continue
            ops.append(op)
        sig = "->".join(ops)
        if used_signatures[sig] >= max_reuse:
            continue
        used_signatures[sig] += 1
        return {
            "operation": "mixed",
            "level": level,
            "signature": sig,
            "pipeline": [{"type": op, "params": random_params(rng, op)} for op in ops],
        }
    ops = ["shift", "xor"]
    return {
        "operation": "mixed",
        "level": "L1",
        "signature": "shift->xor",
        "pipeline": [{"type": op, "params": random_params(rng, op)} for op in ops],
    }


def generate_for_subtype(
    subtype: str,
    count: int,
    seed: int,
    mixed_level_mix: dict[str, float],
    mixed_cov: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    sig_counter: Counter[str] = Counter()
    level_counter: Counter[str] = Counter()
    op_counter: Counter[str] = Counter()

    for i in range(1, count + 1):
        params = (
            build_mixed_params(rng, sig_counter, mixed_level_mix, mixed_cov)
            if subtype == "mixed"
            else random_params(rng, subtype)
        )
        if subtype == "mixed":
            level_counter[params["level"]] += 1
            for step in params["pipeline"]:
                op_counter[step["type"]] += 1

        examples: list[tuple[str, str]] = []
        example_count = rng.randint(8, 10)
        for _ in range(example_count):
            src = rng.randint(0, 255)
            dst = apply_rule(src, subtype, params)
            examples.append((to_bin8(src), to_bin8(dst)))
        query_int = rng.randint(0, 255)
        query = to_bin8(query_int)
        answer = to_bin8(apply_rule(query_int, subtype, params))

        row = {
            "id": f"binary_{subtype}_{i:07d}",
            "subtype": subtype,
            "level": params.get("level", "L1" if subtype != "mixed" else "L1"),
            "prompt": build_train_style_prompt(examples, query),
            "answer": answer,
            "metadata": {"params": params, "query": query, "examples": examples},
        }
        rows.append(row)

    cov = {
        "count": count,
        "subtype": subtype,
        "mixed_level_distribution": dict(level_counter),
        "mixed_operation_distribution": dict(op_counter),
        "mixed_signature_unique_count": len(sig_counter),
        "mixed_signature_max_repetition": max(sig_counter.values()) if sig_counter else 0,
    }
    return rows, cov


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate binary domain candidates.")
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--distribution-file", required=True)
    parser.add_argument("--mixed-config", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default="llama3.1:8b")
    args = parser.parse_args()

    run_root = Path(args.output_root) / args.run_id
    generated_dir = run_root / "generated"
    reports_dir = run_root / "reports"
    generated_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    distribution_cfg = load_json(Path(args.distribution_file))
    counts = compute_counts(args.total, distribution_cfg["subtype_distribution"])
    mixed_cfg = load_json(Path(args.mixed_config))
    mixed_level_mix = mixed_cfg["level_mix"]
    mixed_cov = mixed_cfg["combination_coverage"]

    all_rows: list[dict[str, Any]] = []
    coverage_summary: dict[str, Any] = {}
    for idx, subtype in enumerate(SUBTYPES):
        rows, cov = generate_for_subtype(subtype, counts[subtype], args.seed + idx * 97, mixed_level_mix, mixed_cov)
        all_rows.extend(rows)
        write_jsonl(generated_dir / f"{subtype}_candidates.jsonl", rows)
        coverage_summary[subtype] = cov

    write_jsonl(generated_dir / "all_candidates.jsonl", all_rows)
    dump_json(
        reports_dir / "generation_summary.json",
        {
            "run_id": args.run_id,
            "total_requested": args.total,
            "total_generated": len(all_rows),
            "model": args.model,
            "counts_by_subtype": counts,
            "coverage_summary": coverage_summary,
        },
    )


if __name__ == "__main__":
    main()
