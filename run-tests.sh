#!/usr/bin/env bash
# run-tests.sh -- run the delivered common-keys test suite.
#
# It drives the delivered entry point (`bash common-keys.sh <json-file>`) on the
# hand-built fixtures in tests/common_keys_tests.py, writes the TAP report to
# reports/tests.tap (the path the requirement document names) and exits 0 only
# when every case passes. The suite covers the all-shared case, the
# partially-shared case and the none case, as REQ-006 declares, plus one case
# per open decision AMB-001 .. AMB-004.
#
# A caller can point the runner at another Python file with
# COMMON_KEYS_TEST_FILE so the runner's own exit-code contract stays testable.
set -euo pipefail
cd "$(dirname "$0")"

TEST_FILE="${COMMON_KEYS_TEST_FILE:-tests/common_keys_tests.py}"

if [ ! -f "$TEST_FILE" ]; then
  printf 'run-tests.sh: no test file at %s\n' "$TEST_FILE" >&2
  exit 1
fi

exec python3 "$TEST_FILE"
