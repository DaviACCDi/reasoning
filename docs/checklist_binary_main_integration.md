# Binary Main Integration Checklist

## Pre-Merge Checklist (Per Subtype PR)

- [ ] PR exists and points to `main`.
- [ ] PR branch is `feature/binary-<subtype>`.
- [ ] `config/prompt_final.md` is present.
- [ ] `config/quality_thresholds.json` is present.
- [ ] Validator behavior for subtype is present and unchanged.
- [ ] Scoring behavior for subtype is present and unchanged.
- [ ] `reports/final_quality_report.json` is present.
- [ ] Subtype status is `READY_FOR_PR`.
- [ ] Quality evidence is attached (keep/reject/semantic/score).
- [ ] Export matches `id,prompt,answer`.
- [ ] No unapproved architecture changes.

## Merge Order Checklist

- [ ] 1) `binary/shift`
- [ ] 2) `binary/rotation`
- [ ] 3) `binary/xor`
- [ ] 4) `binary/and`
- [ ] 5) `binary/or`
- [ ] 6) `binary/not`
- [ ] 7) `binary/mixed`

## Post-Merge Checklist (After Each PR)

- [ ] `main` remains healthy.
- [ ] Merged subtype still runs correctly from `main`.
- [ ] Frozen config files are intact.
- [ ] Reports are still accessible.
- [ ] No regression in already merged subtypes.

## Final Integration Checklist (After 7/7)

- [ ] All 7 subtypes are present in `main`.
- [ ] `data/final/binary/binary_train_ready.csv` is preserved.
- [ ] `data/final/binary/binary_train_ready.jsonl` is preserved.
- [ ] `data/final/binary/binary_distribution_summary.json` is preserved.
- [ ] `data/final/binary/binary_pr_consolidation.json` is preserved.
- [ ] `data/final/binary/binary_freeze_manifest.json` is preserved.
- [ ] Binary pipeline runs end-to-end using local model.
- [ ] Documentation reflects binary baseline as integrated.
