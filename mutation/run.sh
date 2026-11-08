#!/usr/bin/env bash
# mutation/run.sh -- mutate the delivered counting behaviour and re-run the
# delivered test suite against each mutant.
#
# Usage: bash mutation/run.sh
#
# Each mutant edits summary.py (the logic summary.sh executes) or summary.sh
# itself in a throwaway copy of the project, then runs `bash run-tests.sh`
# against that copy.  The tool-agnostic report is written to
# reports/mutation/mutation.json as
#
#   {"total": <int>, "survivors": [{"file": ..., "line": ..., "description": ...}]}
#
# The command exits nonzero when any mutant survives, so a test suite that
# cannot fail is never reported as green.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 mutation/run.py "$@"
