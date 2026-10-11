#!/usr/bin/env bash
# Run the full test suite for summary.sh through the process boundary.
# Exits non-zero when any test fails, so a CI or smoke gate can gate on it.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m unittest discover -s tests -p 'test_*.py' -v
