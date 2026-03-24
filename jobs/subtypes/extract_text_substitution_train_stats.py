#!/usr/bin/env python3
"""Extract reference statistics for text/substitution rows from data/raw/train.csv."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

HEADER_MARK = "secret encryption rules are used on text"


def is_substitution_row(prompt: str) -> bool:
    return HEADER_MARK in (prompt or "")


def parse_example_pairs(prompt: str) -> list[tuple[str, str]]:
    body = prompt.split("Here are some examples:")[-1]
    if "Now, decrypt" in body:
        body = body.split("Now, decrypt")[0]
    pairs: list[tuple[str, str]] = []
    for ln in body.strip().splitlines():
        if "->" not in ln:
            continue
        left, right = ln.split("->", 1)
        pairs.append((left.strip(), right.strip()))
    return pairs


def extract_decrypt_cipher(prompt: str) -> str:
    if "Now, decrypt the following text:" not in prompt:
        return ""
    return prompt.split("Now, decrypt the following text:")[-1].strip()


def analyze(rows: list[dict[str, str]]) -> dict[str, Any]:
    n = len(rows)
    prompt_lens = [len(r["prompt"]) for r in rows]
    answer_lens = [len(r["answer"]) for r in rows]
    ex_counts: list[int] = []
    arrow_lines = 0
    for r in rows:
        pairs = parse_example_pairs(r["prompt"])
        ex_counts.append(len(pairs))
        arrow_lines += sum(1 for ln in r["prompt"].splitlines() if "->" in ln)

    return {
        "row_count": n,
        "prompt_length": {
            "min": min(prompt_lens),
            "max": max(prompt_lens),
            "avg": round(sum(prompt_lens) / n, 4),
        },
        "answer_length_chars": {
            "min": min(answer_lens),
            "max": max(answer_lens),
            "avg": round(sum(answer_lens) / n, 4),
        },
        "examples_per_prompt": {
            "min": min(ex_counts),
            "max": max(ex_counts),
            "avg": round(sum(ex_counts) / n, 4),
        },
        "lines_with_arrow_total": arrow_lines,
        "decrypt_task": {
            "now_decrypt_count": sum(1 for r in rows if "Now, decrypt the following text:" in r["prompt"]),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-csv", default="data/raw/train.csv")
    parser.add_argument(
        "--out",
        default="data/subtypes/text/substitution/_shared/reports/train_reference_stats.json",
    )
    args = parser.parse_args()

    train_path = Path(args.train_csv)
    rows = [r for r in csv.DictReader(train_path.open(encoding="utf-8", newline="")) if is_substitution_row(r.get("prompt", ""))]

    payload = {
        "source": str(train_path.as_posix()),
        "filter": HEADER_MARK,
        "stats": analyze(rows),
        "sample_ids": [rows[i]["id"] for i in range(min(5, len(rows)))],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
