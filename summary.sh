#!/usr/bin/env bash
# summary.sh -- per-region revenue and average order value from a CSV.
#
# Usage: bash summary.sh <csv>
#
# Contract (docs/requirements/intake.yaml, deliverable block):
#   run:          bash summary.sh {csv}
#   region line:  <region> <count> <sum> <mean>
#   total line:   TOTAL <count> <sum>
#   skipped line: SKIPPED <skipped-count>
#
# There is no install or build step: the work happens in summary.py using only
# the Python 3 standard library, so the command needs no network access.  The
# input file is only ever opened for reading.
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
