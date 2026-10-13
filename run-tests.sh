#!/usr/bin/env bash
# run-tests.sh -- run the delivered common-keys test suite.
#
# It drives the delivered entry point (`bash common-keys.sh <json-file>`) on the
# hand-built fixtures in tests/common_keys_tests.py, writes the TAP report to
# reports/tests.tap (the path the requirement document names) and exits 0 only
# when every case passes. The suite covers the all-shared case, the
# partially-shared case and the none case, plus one case per open decision
# AMB-001 .. AMB-003.
#
# The declared TAP report is also echoed to standard output. A test consumer
# reads the runner's stdout for a known summary shape (`# tests N`, `# pass N`,
# `# fail 0`); a report that lived only in a file would look like "no test
# summary found" and the run's smoke gate would fail closed on a deliverable
# that actually passes. The echo comes after the suite, so the summary stays at
# the end of the stream and survives a bounded `tail`.
#
# A caller can point the runner at another Python file with
# COMMON_KEYS_TEST_FILE so the runner's own exit-code contract stays testable;
# in that mode the delivered report path is not touched.
set -euo pipefail
cd "$(dirname "$0")"

TEST_FILE="${COMMON_KEYS_TEST_FILE:-tests/common_keys_tests.py}"

if [ ! -f "$TEST_FILE" ]; then
  printf 'run-tests.sh: no test file at %s\n' "$TEST_FILE" >&2
  exit 1
fi

set +e
python3 "$TEST_FILE"
status=$?
set -e

if [ "$TEST_FILE" = "tests/common_keys_tests.py" ] && [ -f reports/tests.tap ]; then
  cat reports/tests.tap
fi

exit "$status"
