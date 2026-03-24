#!/usr/bin/env bash
set -euo pipefail

python jobs/domains/binary/run_binary_domain.py "$@"
