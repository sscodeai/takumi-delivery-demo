#!/usr/bin/env bash
# mutation.sh -- mutation-detection harness for the delivered summary tool.
#
# Usage: bash mutation.sh
#
# Applies one deliberate defect at a time to summary.py, runs the delivered test
# suite against each mutant, and writes reports/mutation/mutation.json:
#
#   {"total": <mutants measured>,
#    "survivors": [{"file": ..., "line": ..., "description": ...}, ...]}
#
# A mutant the suite still passes is a survivor (a test gap); the harness exits
# non-zero when any survives. There is no install step and no network access:
# the harness is Python 3 standard library only.
set -euo pipefail
cd "$(dirname "$0")"

exec python3 mutation/mutation.py "$@"
