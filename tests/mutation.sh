#!/usr/bin/env bash
# tests/mutation.sh -- mutate the counting behaviour and re-run the suite.
#
# Usage: bash tests/mutation.sh
#
# Each mutant edits summary.py (the counting logic behind summary.sh) in a
# throwaway copy of the project and re-runs `bash run-tests.sh` against it.
# The tool-agnostic survivors report is written to
# reports/mutation/mutation.json.  The command exits non-zero if any mutant
# survives, so a test suite that cannot fail is not reported as green.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 tests/mutation_runner.py
