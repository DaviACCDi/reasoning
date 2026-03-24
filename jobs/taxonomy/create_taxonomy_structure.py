#!/usr/bin/env python3
"""Materialize fixed taxonomy structure for subtype-oriented operation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

RAW_DATASET_TOTAL = 9500
TAXONOMY_SOURCE = "fixed analysis of data/raw/train.csv"

OFFICIAL_TAXONOMY = {
    "binary": {
        "shift": 1602,
    },
    "logic": {
        "formula": 1597,
        "mapping": 1594,
        "roman": 1576,
        "symbolic": 1555,
    },
    "text": {
        "substitution": 1576,
    },
}

SUBTYPE_FOLDERS = (
    "source",
    "generated",
    "validated",
    "reviewed",
    "rejected",
    "final",
    "reports",
    "config",
)


def build_manifest_payload() -> dict:
    subtypes: list[dict[str, object]] = []
    level_totals: dict[str, int] = {}
    total = 0

    for problem_type, groups in OFFICIAL_TAXONOMY.items():
        level_total = sum(groups.values())
        level_totals[problem_type] = level_total
        total += level_total

        for subgroup, observed_count in groups.items():
            subtypes.append(
                {
                    "problem_type": problem_type,
                    "subgroup": subgroup,
                    "path": f"{problem_type}/{subgroup}",
                    "observed_count_in_raw_train": observed_count,
                }
            )

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": TAXONOMY_SOURCE,
            "is_dynamic_discovery": False,
            "notes": "Taxonomy is fixed and intentionally hardcoded.",
        },
        "totals": {
            "raw_train_rows": RAW_DATASET_TOTAL,
            "sum_of_subtype_counts": total,
            "matches_raw_total": total == RAW_DATASET_TOTAL,
        },
        "types": [
            {
                "problem_type": problem_type,
                "observed_count_in_raw_train": level_totals[problem_type],
                "subgroups": list(groups.keys()),
            }
            for problem_type, groups in OFFICIAL_TAXONOMY.items()
        ],
        "subtypes": subtypes,
    }


def create_subtype_structure(output_root: Path) -> int:
    created = 0
    for problem_type, groups in OFFICIAL_TAXONOMY.items():
        for subgroup in groups:
            subtype_root = output_root / problem_type / subgroup
            for folder in SUBTYPE_FOLDERS:
                (subtype_root / folder).mkdir(parents=True, exist_ok=True)
            created += 1
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Create fixed subtype folder structure.")
    parser.add_argument("--output-root", default="data/subtypes")
    parser.add_argument("--manifest-out", default="data/taxonomy/taxonomy_manifest.json")
    parser.add_argument("--skip-manifest", action="store_true")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest_out)

    created = create_subtype_structure(output_root)
    print(f"Subtype roots materialized: {created}")
    print(f"Output root: {output_root}")

    if not args.skip_manifest:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = build_manifest_payload()
        manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    main()
