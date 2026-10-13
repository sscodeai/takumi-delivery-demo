#!/usr/bin/env bash
# run-tests.sh -- run the delivered pathfind test suite.
#
# It drives the delivered entry point (`bash pathfind.sh <mapfile>`) on the
# hand-built maps in tests/pathfind_tests.py, writes the TAP report to
# reports/tests.tap (the path the requirement document names) and exits 0 only
# when every case passes. The suite includes an assertion on a reachable map,
# one on a map that requires routing around walls, and one on the unreachable
# case, as REQ-004 declares, and one case per open decision AMB-001 .. AMB-003.
#
# A caller can point the runner at another Python file with PATHFIND_TEST_FILE
# so the runner's own exit-code contract stays testable.
set -euo pipefail
cd "$(dirname "$0")"

TEST_FILE="${PATHFIND_TEST_FILE:-tests/pathfind_tests.py}"

if [ ! -f "$TEST_FILE" ]; then
  printf 'run-tests.sh: no test file at %s\n' "$TEST_FILE" >&2
  exit 1
fi

exec python3 "$TEST_FILE"
