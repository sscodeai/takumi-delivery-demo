#!/usr/bin/env bash
# Run the full test suite for summary.sh through the process boundary.
# Exits non-zero when any test fails (or when no test is discovered), so a CI or
# smoke gate can gate on it.
#
# TESTS_DIR and TEST_PATTERN may be overridden by the caller. They exist so the
# runner's exit-code contract can itself be tested with a controlled directory;
# the defaults are the repository suite.
set -euo pipefail
cd "$(dirname "$0")"

TESTS_DIR="${TESTS_DIR:-tests}"
TEST_PATTERN="${TEST_PATTERN:-test_*.py}"

# A discovery that finds nothing must not look like a passing suite: a dropped
# test file would otherwise let the smoke gate go green with nothing run.
if ! find "$TESTS_DIR" -type f -name "$TEST_PATTERN" -print -quit | grep -q .; then
  printf 'run-tests.sh: no tests matched %s under %s\n' "$TEST_PATTERN" "$TESTS_DIR" >&2
  exit 1
fi

exec python3 -m unittest discover -s "$TESTS_DIR" -p "$TEST_PATTERN" -v
