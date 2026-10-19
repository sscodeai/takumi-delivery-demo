#!/usr/bin/env bash
# run-tests.sh -- run the delivered test suites.
#
# The confirmed requirement document (docs/requirements/intake.yaml) declares
# this runner:
#
#   scenarios:
#     - id: SCN-001
#       run: "bash run-tests.sh"
#       report: tap
#       report_path: "reports/tests.tap"
#
# It drives the delivered entry points and writes the TAP report to
# reports/tests.tap (the path the document names) and exits 0 only when every
# delivered case passes.
#
# Two suites ship:
#
#   * tests/common_keys_tests.py -- the declared suite for this delivery. It
#     drives `bash common-keys.sh <json-file>` and writes reports/tests.tap.
#   * tests/test_*.py -- the earlier summary.sh CLI suite (unittest) for the
#     CSV summariser this repository also carries, so the smoke gate's summary
#     entry point stays green.
#
# The summary suite runs first and writes only to stderr; the declared TAP
# report is echoed to standard output LAST, so a test consumer that reads the
# runner's stdout for a known summary shape (`# tests N`, `# pass N`, `# fail 0`)
# finds it at the end of the stream even after a bounded `tail`.
#
# Before the report is echoed, tests/verify_tap_report.py checks the artifact
# itself (REQ-005): it must be TAP version 13 with a 1..N plan, no `not ok`
# point, and a zero failure total. That way the runner's exit status reflects
# the report the requirement document tells SCN-001 to read, not merely the
# suite's own exit code.
#
# A caller can point the runner at another Python file with
# COMMON_KEYS_TEST_FILE so the runner's own exit-code contract stays testable;
# in that mode the delivered report path is not touched and the summary suite is
# not run.
set -euo pipefail
cd "$(dirname "$0")"

TEST_FILE="${COMMON_KEYS_TEST_FILE:-tests/common_keys_tests.py}"

if [ ! -f "$TEST_FILE" ]; then
  printf 'run-tests.sh: no test file at %s\n' "$TEST_FILE" >&2
  exit 1
fi

summary_status=0
if [ "$TEST_FILE" = "tests/common_keys_tests.py" ]; then
  # The summary.sh CLI suite (unittest discovery over tests/test_*.py). Its
  # output goes to stderr so stdout stays the TAP stream the smoke gate reads.
  set +e
  python3 -m unittest discover -s tests -p 'test_*.py' 1>&2
  summary_status=$?
  set -e
fi

set +e
python3 "$TEST_FILE"
status=$?
set -e

verifier_status=0
if [ "$TEST_FILE" = "tests/common_keys_tests.py" ]; then
  # REQ-005: validate the declared artifact before it is echoed. The verifier
  # writes to stderr so the TAP report stays the last thing on stdout.
  set +e
  python3 tests/verify_tap_report.py 1>&2
  verifier_status=$?
  set -e
fi

if [ "$TEST_FILE" = "tests/common_keys_tests.py" ] && [ -f reports/tests.tap ]; then
  cat reports/tests.tap
fi

if [ "$summary_status" -ne 0 ]; then
  exit "$summary_status"
fi
if [ "$status" -ne 0 ]; then
  exit "$status"
fi
if [ "$verifier_status" -ne 0 ]; then
  exit "$verifier_status"
fi
exit 0
