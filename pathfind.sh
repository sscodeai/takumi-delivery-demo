#!/usr/bin/env bash
# pathfind.sh -- the shortest path from S to E in a grid map, in steps.
#
# Usage: bash pathfind.sh <mapfile>
#
# Contract (docs/requirements/intake.yaml):
#   run: bash pathfind.sh {map}
#   stdout: the number of moves on a shortest S-to-E path, or the lowercase
#           word 'unreachable' when no path exists; exit 0 either way.
#   a map that violates the format is a stop-error (AMB-003): a diagnostic on
#   stderr and a non-zero exit.
#
#   '#' is a wall, '.' is a free cell, 'S' is the single start and 'E' is the
#   single exit; S and E are passable cells. Steps are orthogonal (AMB-001):
#   only the four edge-adjacent neighbours up, down, left and right are
#   adjacent, and every move costs one step, so the printed number is the
#   number of moves made (AMB-002).
#
# The search lives in pathfind.py (Python 3 standard library only), so it needs
# no install step and no network access; this wrapper is the declared entry
# point and keeps the usage contract in one place.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  printf 'usage: bash pathfind.sh <mapfile>\n' >&2
  exit 2
fi

exec python3 "$(dirname "$0")/pathfind.py" "$@"
