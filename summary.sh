#!/usr/bin/env bash
# summary.sh -- per-suite pass percentage from a CSV of test-run records.
#
# Usage: bash summary.sh <csv>
#
# Contract (docs/requirements/intake.yaml, deliverable block):
#   run:          bash summary.sh {csv}
#   suite line:   <suite> <passed> <total> <percentage>
#   total line:   TOTAL <passed_sum> <total_sum>
#
# There is no install or build step: the work happens in summary.py using only
# the Python 3 standard library, so the command needs no network access and no
# interactive input.  The input file is only ever opened for reading.
#
# The decisions this delivery settled live in docs/decisions.md; in the source
# they are marked with greppable `AMB-00n` comments (see summary.py).
set -euo pipefail

if [ "$#" -ne 1 ]; then
  printf 'usage: bash summary.sh <csv>\n' >&2
  exit 2
fi

here="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$here/summary.py" "$1"
