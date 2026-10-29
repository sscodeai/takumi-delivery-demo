#!/usr/bin/env bash
# summary.sh -- per-region revenue and average order value from a sales CSV.
#
# Usage: bash summary.sh <csv>
#
# Contract (docs/requirements/intake.yaml, deliverable block):
#   run:          bash summary.sh {csv}
#   region line:  <region> <count> <sum> <mean>
#   total line:   TOTAL <count> <sum>
#   skipped line: SKIPPED <skipped-count>
#
# REQ-001: this shell script at the repository root is the single entry point.
# It takes the CSV path from $1, reads that file and writes the report to
# standard output. There is no install step and no build step: the work happens
# in summary.py using only the Python 3 standard library, and the script reads
# exactly one local file so it runs with the network disabled.
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
