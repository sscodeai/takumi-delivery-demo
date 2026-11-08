#!/usr/bin/env bash
# run-tests.sh -- run the delivered test suites and write TAP reports.
#
# Usage: bash run-tests.sh
#
# The delivery's own suites for the current requirement are
#   tests/test_summary.py       acceptance: drives `bash summary.sh` against the
#                               checked-in fixtures in tests/fixtures/ and
#                               writes reports/tests.tap;
#   tests/test_summary_units.py unit: imports summary.py and checks the helper
#                               rules behind every criterion and every AMB-nnn
#                               decision, writing
#                               reports/tests-summary-units.tap.
#
# The inherited `passrate` and `region` tools from earlier deliveries in this
# repository are not part of this requirement and are not run here.
#
# TAP_OUT lets the mutation harness point the reports at a throwaway directory,
# so a mutant run never overwrites the delivered report.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p reports

tap_out="${TAP_OUT:-reports/tests.tap}"
unit_tap="${tap_out%.tap}-summary-units.tap"

status=0
set +e
TAP_OUT="$tap_out" python3 tests/test_summary.py
acceptance_status=$?
TAP_OUT="$unit_tap" python3 tests/test_summary_units.py
unit_status=$?
set -e

if [ "$acceptance_status" -ne 0 ]; then
  status="$acceptance_status"
fi
if [ "$unit_status" -ne 0 ]; then
  status="$unit_status"
fi
exit "$status"
