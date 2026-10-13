#!/usr/bin/env bash
# common-keys.sh -- the keys common to every object in a JSON array.
#
# Usage: bash common-keys.sh <json-file>
#
# Contract (docs/requirements/intake.yaml):
#   run:    "bash common-keys.sh <json-file>"
#   stdout: one common key per line, in ascending alphabetical order, or the
#           single lowercase word `none` when no key is common; exit 0.
#   a file that is not a JSON array is a stop-error (AMB-003): a diagnostic on
#   stderr and a non-zero exit, with no key list on stdout.
#   an array element that is not an object is skipped (AMB-002); an array with
#   no object at all prints `none` and exits 0 (AMB-001).
#
# The logic lives in common_keys.py (Python 3 standard library only), so the
# command needs no install step and no network access; this wrapper is the
# declared entry point and keeps the usage contract in one place.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  printf 'usage: bash common-keys.sh <json-file>\n' >&2
  exit 2
fi

exec python3 "$(dirname "$0")/common_keys.py" "$@"
