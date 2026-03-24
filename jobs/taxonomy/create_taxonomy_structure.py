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
}

# text/substitution split into operational variants under data/subtypes/text/substitution/<variant>/
# Only custom_mapping has non-zero train count (1576); others are synthetic extensions.
TEXT_SUBSTITUTION_VARIANTS: dict[str, int] = {
    "caesar_shift": 0,
    "reverse_alphabet": 0,
    "custom_mapping": 1576,
    "number_mapping": 0,
    "mixed": 0,
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

    text_subst_total = sum(TEXT_SUBSTITUTION_VARIANTS.values())
    level_totals["text"] = text_subst_total
    total += text_subst_total

    for variant, observed_count in TEXT_SUBSTITUTION_VARIANTS.items():
        subtypes.append(
            {
                "problem_type": "text",
                "subgroup": f"substitution/{variant}",
                "path": f"text/substitution/{variant}",
                "observed_count_in_raw_train": observed_count,
                "notes": (
                    "train anchor row pattern"
                    if variant == "custom_mapping"
                    else "synthetic variant; not isolated as own label in raw train"
                ),
            }
        )

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": TAXONOMY_SOURCE,
            "is_dynamic_discovery": False,
            "notes": "Taxonomy is fixed and intentionally hardcoded. text/substitution uses nested variants.",
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
        ]
        + [
            {
                "problem_type": "text",
                "observed_count_in_raw_train": text_subst_total,
                "subgroups": [f"substitution/{v}" for v in TEXT_SUBSTITUTION_VARIANTS],
            }
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

    subst_root = output_root / "text" / "substitution"
    for variant in TEXT_SUBSTITUTION_VARIANTS:
        for folder in SUBTYPE_FOLDERS:
            (subst_root / variant / folder).mkdir(parents=True, exist_ok=True)
        created += 1

    (subst_root / "_shared" / "reports").mkdir(parents=True, exist_ok=True)
    (subst_root / "_shared" / "source").mkdir(parents=True, exist_ok=True)

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
