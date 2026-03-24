#!/usr/bin/env bash
# Create feature branches for text/substitution calibration from foundation (local git only).
# Run from repo root after: git fetch origin
set -euo pipefail
BASE="feature/text-substitution-foundation"
BRANCHES=(
  "feature/text-substitution-custom-mapping"
  "feature/text-substitution-reverse-alphabet"
  "feature/text-substitution-caesar-shift"
  "feature/text-substitution-number-mapping"
  "feature/text-substitution-mixed"
)

echo "Base branch: $BASE"
echo "Ensure you are up to date: git checkout $BASE && git pull origin $BASE"
echo ""
for b in "${BRANCHES[@]}"; do
  echo "git checkout $BASE && git pull origin $BASE && git checkout -b $b && git push -u origin $b"
done
