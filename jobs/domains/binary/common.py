#!/usr/bin/env python3
"""Shared utilities for binary domain local dataset pipeline."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

SUBTYPES = ("shift", "rotation", "xor", "and", "or", "not", "mixed")
OPS = ("shift", "rotation", "xor", "and", "or", "not")


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
        current = value
        for step in params["pipeline"]:
            current = apply_rule(current, step["type"], step["params"])
        return current
    raise ValueError(f"Unsupported subtype: {subtype}")


def random_params(rng: random.Random, subtype: str) -> dict[str, Any]:
    if subtype == "shift":
        return {"operation": rng.choice(["left_shift", "right_shift"]), "amount": rng.randint(1, 3)}
    if subtype == "rotation":
        return {"operation": rng.choice(["rotate_left", "rotate_right"]), "amount": rng.randint(1, 3)}
    if subtype in {"xor", "and", "or"}:
        return {"operation": subtype, "mask": rng.randint(1, 255)}
    if subtype == "not":
        return {"operation": "not"}
    raise ValueError(f"Unsupported primitive subtype: {subtype}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


TRAIN_STYLE_HEADER = (
    "In Alice's Wonderland, a secret bit manipulation rule transforms 8-bit binary numbers. "
    "The transformation involves operations like bit shifts, rotations, XOR, AND, OR, NOT, "
    "and possibly majority or choice functions."
)


def build_train_style_prompt(examples: list[tuple[str, str]], query: str) -> str:
    lines = [
        TRAIN_STYLE_HEADER,
        "Here are some examples of input -> output:",
    ]
    lines.extend([f"{src} -> {dst}" for src, dst in examples])
    lines.append("")
    lines.append(f"Now, determine the output for: {query}")
    return "\n".join(lines)
