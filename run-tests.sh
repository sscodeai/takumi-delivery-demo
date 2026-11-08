#!/usr/bin/env bash
# run-tests.sh -- run the delivered ticket-summary test suite and write TAP.
#
# Usage: bash run-tests.sh
#
# The delivery's own suites are
#   tests/test_ticket_summary.py       integration: drives `bash ticket-summary.sh`
#                                      against the contract in
#                                      docs/requirements/intake.yaml and writes
#                                      reports/tests.tap;
#   tests/test_ticket_summary_units.py unit: imports ticket_summary.py and checks
#                                      the rules behind every criterion and every
#                                      AMB-nnn decision, writing
#                                      reports/tests-ticket-units.tap.
#
# TAP_OUT lets the mutation harness point the reports at a throwaway directory,
# so a mutant run never overwrites the delivered report.
#
# Suites inherited from earlier deliveries in this reused repository (summary.sh
# and passrate.sh) are still run when their files are present, into separate
# reports, so those tools keep their coverage.  They are not part of this
# requirement, and a checkout that only carries the ticket delivery (for example
# a mutation sandbox) simply skips them.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p reports

tap_out="${TAP_OUT:-reports/tests.tap}"
unit_tap="${tap_out%.tap}-ticket-units.tap"

status=0

set +e
TAP_OUT="$tap_out" python3 tests/test_ticket_summary.py
ticket_status=$?
TAP_OUT="$unit_tap" python3 tests/test_ticket_summary_units.py
unit_status=$?
set -e

if [ "$ticket_status" -ne 0 ]; then
  status="$ticket_status"
fi
if [ "$unit_status" -ne 0 ]; then
  status="$unit_status"
fi

for inherited in tests/test_summary.py tests/test_summary_units.py tests/test_passrate.py; do
  if [ -f "$inherited" ]; then
    inherited_tap="${tap_out%.tap}-inherited-$(basename "${inherited%.py}").tap"
    set +e
    TAP_OUT="$inherited_tap" python3 "$inherited"
    inherited_status=$?
    set -e
    if [ "$inherited_status" -ne 0 ] && [ "$status" -eq 0 ]; then
      status="$inherited_status"
    fi
  fi
done

exit "$status"
