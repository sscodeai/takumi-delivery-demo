#!/usr/bin/env bash
# run-tests.sh -- run the delivered test suite and write the TAP report.
#
# Usage: bash run-tests.sh
#
# The suite drives the delivered entry point (`bash summary.sh <csv>`) in
# subprocesses and asserts the contract in docs/requirements/intake.yaml. The
# report is written to reports/tests.tap and echoed to stdout; this runner exits
# 0 only when every delivered check passes.
#
# TAP_OUT lets the mutation harness point the same suite at a throwaway report,
# so a mutant run never overwrites the delivered report.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p reports

set +e
TAP_OUT="${TAP_OUT:-reports/tests.tap}" python3 tests/test_summary.py
status=$?
set -e

exit "$status"
