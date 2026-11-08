#!/usr/bin/env bash
# run-tests.sh -- run the delivered test suites and write a TAP report.
#
# Usage: bash run-tests.sh
#
# The delivery's suites are
#   tests/test_summary.py        acceptance: drives `bash summary.sh` against
#                                the checked-in fixtures in tests/fixtures/ and
#                                the declared sample, writing reports/tests.tap;
#   tests/test_summary_units.py  unit: imports summary.py and checks the helper
#                                rules behind every criterion and every AMB-nnn
#                                decision, writing reports/tests-units.tap;
#   tests/test_contract.py       delivery contract: checks the TAP reports, the
#                                mutation harness and the decision record,
#                                writing reports/tests-contract.tap.
#
# The inherited `passrate` tool from an earlier delivery in this repository is
# not part of this requirement and is not run here.
#
# TAP_OUT lets the mutation harness point the reports at a throwaway directory,
# so a mutant run never overwrites the delivered report.
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
TAP_OUT="$tap_out" CONTRACT_TAP_OUT="$contract_tap" python3 tests/test_contract.py
contract_status=$?
set -e

for code in "$acceptance_status" "$unit_status" "$contract_status"; do
  if [ "$code" -ne 0 ]; then
    status="$code"
  fi
done
exit "$status"
