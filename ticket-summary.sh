#!/usr/bin/env bash
# ticket-summary.sh -- open/closed support-ticket counts per assignee.
#
# Usage: bash ticket-summary.sh <csv>
#
# Contract (docs/requirements/intake.yaml, deliverable block):
#   run:           bash ticket-summary.sh {csv}
#   assignee line: <assignee> <open> <closed>
#   total line:    TOTAL <open-sum> <closed-sum>
#
# REQ-001: this shell script at the repository root is the single entry point.
# It takes the CSV path from $1, reads that one file and writes the report to
# standard output.  There is no install or build step: the work happens in
# ticket_summary.py using only the Python 3 standard library, so the command
# needs no network access.
#
# The decisions this delivery settled live in docs/decisions.md; in the source
# they are marked with greppable `AMB-00n` comments (see ticket_summary.py).
set -euo pipefail

if [ "$#" -ne 1 ]; then
  printf 'usage: bash ticket-summary.sh <csv>\n' >&2
  exit 2
fi

here="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$here/ticket_summary.py" "$1"
