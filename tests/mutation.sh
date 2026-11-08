#!/usr/bin/env bash
# tests/mutation.sh -- compatibility entry point for the mutation check.
#
# Usage: bash tests/mutation.sh
#
# The harness itself lives in mutation/run.py and is invoked as
# `bash mutation/run.sh` (the command docs/requirements/intake.yaml declares).
# This wrapper is kept so the older path still works.
set -euo pipefail
cd "$(dirname "$0")/.."
exec bash mutation/run.sh "$@"
