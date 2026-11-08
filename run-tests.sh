#!/usr/bin/env bash
# run-tests.sh -- run the delivered test suites and write TAP reports.
#
# Usage: bash run-tests.sh
#
# The delivery's own suites for the current requirement are
#   tests/test_summary.py       integration: drives `bash summary.sh` against the
#                               contract in docs/requirements/intake.yaml
#                               (region lines, SKIPPED, TOTAL) and writes
#                               reports/tests.tap;
#   tests/test_summary_units.py unit: imports summary.py and checks the helper
#                               rules behind every criterion and every AMB-nnn
#                               decision, writing reports/tests-summary-units.tap.
# The inherited suite from the previous delivery in this repository
# (tests/test_passrate.py plus tests/test_units.py, for passrate.sh) is still
# run, into reports/tests-passrate.tap, so that tool keeps its coverage; its
# result also counts toward this runner's exit status.
#
# TAP_OUT lets the mutation harness point the reports at a throwaway directory,
# so a mutant run never overwrites the delivered report.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p reports

tap_out="${TAP_OUT:-reports/tests.tap}"
unit_tap="${tap_out%.tap}-summary-units.tap"
inherited_tap="${tap_out%.tap}-passrate.tap"

status=0
set +e
TAP_OUT="$tap_out" python3 tests/test_summary.py
summary_status=$?
TAP_OUT="$unit_tap" python3 tests/test_summary_units.py
unit_status=$?
TAP_OUT="$inherited_tap" python3 tests/test_passrate.py
inherited_status=$?
set -e

if [ "$summary_status" -ne 0 ]; then
  status="$summary_status"
fi
if [ "$unit_status" -ne 0 ]; then
  status="$unit_status"
fi
if [ "$inherited_status" -ne 0 ]; then
  status="$inherited_status"
fi
exit "$status"
