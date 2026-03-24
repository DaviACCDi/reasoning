# Merge Playbook: Binary Domain

## Context

This playbook integrates the validated `binary` domain into `main` as the official baseline.

Source-of-truth manifests:

- `data/final/binary/binary_distribution_summary.json`
- `data/final/binary/binary_pr_consolidation.json`
- `data/final/binary/binary_freeze_manifest.json`

Binary domain scope:

- `binary/shift`
- `binary/rotation`
- `binary/xor`
- `binary/and`
- `binary/or`
- `binary/not`
- `binary/mixed`

Validated final dataset:

- `data/final/binary/binary_train_ready.csv`
- `data/final/binary/binary_train_ready.jsonl`
- Total rows: `7000`
- Distribution: `1000` per subtype

## Recommended Merge Order

1. `binary/shift`
2. `binary/rotation`
3. `binary/xor`
4. `binary/and`
5. `binary/or`
6. `binary/not`
7. `binary/mixed`

Rationale: deterministic primitives first, composed subtype (`mixed`) last.

## Dependencies And Cautions

- Keep the winning architecture unchanged:
  - train-style prompt structure
  - implicit rule in prompt
  - programmatic answer as source of truth
  - validator checks prompt examples against internal rule
  - final export schema `id,prompt,answer`
- Do not merge architectural refactors in the same PR sequence.
- Preserve frozen files listed in `binary_freeze_manifest.json`.

## Pre-Merge Verification (Per PR)

For each subtype PR, confirm:

1. PR exists and matches `feature/binary-<subtype>`.
2. `prompt_final.md` is present and frozen.
3. `quality_thresholds.json` is present and frozen.
4. Validator logic for subtype is present in pipeline.
5. Scoring logic is present and unchanged from validated baseline.
6. Final report exists: `reports/final_quality_report.json`.
7. Subtype status is `READY_FOR_PR`.
8. Evidence of quality is attached (metrics and report).
9. Export output is aligned to train schema (`id,prompt,answer`).
10. No unapproved architectural change is included.

## Post-Merge Verification (After Each Merge)

After merging each subtype PR into `main`:

1. `main` builds/runs without regression.
2. Subtype pipeline still executes correctly from `main`.
3. Subtype frozen config files remain unchanged.
4. Reports remain accessible in expected paths.
5. Previously merged subtypes still pass baseline checks.

## Final Validation (After All 7 Merges)

Run final integration checks:

1. All 7 binary subtypes present in `main`.
2. Manifests are preserved:
   - `binary_distribution_summary.json`
   - `binary_pr_consolidation.json`
   - `binary_freeze_manifest.json`
3. Consolidated dataset preserved:
   - `binary_train_ready.csv`
   - `binary_train_ready.jsonl`
4. Binary pipeline executes end-to-end with local model.
5. Documentation reflects official binary baseline state.

## Artifacts That Must Be Preserved

- `data/final/binary/binary_train_ready.csv`
- `data/final/binary/binary_train_ready.jsonl`
- `data/final/binary/binary_distribution_summary.json`
- `data/final/binary/binary_pr_consolidation.json`
- `data/final/binary/binary_freeze_manifest.json`
