# Binary Domain Completion Record

## Status

**READY FOR MAIN INTEGRATION**

Binary domain is completed, validated, and consolidated.

## Covered Subtypes

- `binary/shift`
- `binary/rotation`
- `binary/xor`
- `binary/and`
- `binary/or`
- `binary/not`
- `binary/mixed`

## Final Dataset

- `data/final/binary/binary_train_ready.csv`
- `data/final/binary/binary_train_ready.jsonl`
- Total rows: `7000`
- Target distribution: `1000` rows per subtype
- Distribution status: balanced

## Aggregated Quality

From `data/final/binary/binary_distribution_summary.json`:

- Keep rate: `1.0` for all subtypes
- Reject rate: `0.0` for all subtypes
- Semantic valid rate: `1.0` for all subtypes
- Average score: `1.0` for all subtypes

## Local Model Used

- Provider: local
- Default calibration model: `llama3.1:8b`

## Winning Architecture Pattern

- Prompt aligned to train-style structure
- Rule implicit in prompt examples
- Programmatic answer as source of truth
- Validator checks example consistency against internal rule
- Final export schema: `id,prompt,answer`

## Freeze And Integration Manifests

- `data/final/binary/binary_freeze_manifest.json`
- `data/final/binary/binary_pr_consolidation.json`
- `data/final/binary/binary_merge_execution_plan.json`
- `data/final/binary/binary_final_integration_checklist.json`

## Integration Note

Binary domain is approved as baseline for integration into `main` using the merge order and controls defined in:

- `docs/merge_playbook_binary.md`
- `docs/checklist_binary_main_integration.md`
