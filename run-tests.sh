#!/usr/bin/env bash
# run-tests.sh -- run the delivered test suites and write TAP reports.
#
# Usage: bash run-tests.sh
#
# The delivery's suites are
#   tests/test_summary.py        acceptance: drives `bash summary.sh` against
#                                the checked-in fixtures and the declared sample;
#   tests/test_summary_units.py  unit: imports summary.py and checks the helpers
#                                behind every criterion and AMB-nnn decision;
#   tests/test_contract.py       delivery contract: the entry point, the kept
#                                pipeline, the sample and the decision record.
#
# The inherited `passrate` tool and the earlier summary mutation harness in
# this reused repository are not part of this requirement and are not run here.
#
# TAP_OUT lets a caller point the reports at a throwaway directory.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p reports

tap_out="${TAP_OUT:-reports/tests.tap}"
unit_tap="${tap_out%.tap}-units.tap"
contract_tap="${tap_out%.tap}-contract.tap"

status=0
set +e
TAP_OUT="$tap_out" python3 tests/test_summary.py
acceptance_status=$?
TAP_OUT="$unit_tap" python3 tests/test_summary_units.py
unit_status=$?
CONTRACT_TAP_OUT="$contract_tap" python3 tests/test_contract.py
contract_status=$?
set -e

for code in "$acceptance_status" "$unit_status" "$contract_status"; do
  if [ "$code" -ne 0 ]; then
    status="$code"
  fi
done
exit "$status"
