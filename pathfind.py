#!/usr/bin/env python3
"""Shortest-path search over a grid map (the behaviour behind pathfind.sh).

The grid format and the chosen decisions live in docs/requirements/intake.yaml:

    AMB-001 orthogonal  only the four edge-adjacent moves (up, down, left,
                        right) are allowed, each costing one step
    AMB-002 edges       the printed number is the number of moves made, so a
                        start adjacent to the exit prints 1
    AMB-003 reject      a map that is not one rectangle over '#', '.', 'S' and
                        'E' with exactly one S and one E prints a diagnostic on
                        stderr and exits non-zero

A map with a route prints only the decimal move count; a map whose exit no
route reaches prints the lowercase word 'unreachable'; both exit 0.

Nothing in this module touches the network, reads a second file, or depends on
anything outside the Python 3 standard library.
"""

import sys
from collections import deque

# The map alphabet. A cell is passable when it is not a wall; the wall is the
# only cell a step may not enter, so S and E are passable too.
WALL = "#"
FREE = "."
START = "S"
EXIT = "E"
PASSABLE = (FREE, START, EXIT)

# AMB-001 orthogonal adjacency: the four edge-adjacent neighbours, each one
# step. The diagonals are deliberately absent, so a diagonal shortcut never
# shortens a route.
NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


class MapError(Exception):
    """A map that violates the declared format (AMB-003, reject)."""


def parse(text):
    """Return (rows, start, exit) for a well-formed map, else raise MapError.

    Leading and trailing whitespace (including carriage returns) is stripped
    from every line and blank lines are skipped, so an editor's CRLF, a stray
    blank line or indentation is not a format error. What remains must be a
    rectangle over the map alphabet with exactly one 'S' and exactly one 'E'.
    """
    rows = []
    for raw in text.split("\n"):
        line = raw.strip()
        if line == "":
            continue
        rows.append(line)
    if not rows:
        raise MapError("the map holds no rows")

    width = len(rows[0])
    for index, row in enumerate(rows, start=1):
        if len(row) != width:
            raise MapError(
                "row %d is %d cells wide where row 1 is %d" % (index, len(row), width)
            )
        for column, cell in enumerate(row, start=1):
            if cell not in PASSABLE and cell != WALL:
                raise MapError(
                    "row %d column %d holds %r, which is not one of # . S E"
                    % (index, column, cell)
                )

    starts = [
        (row, column)
        for row, line in enumerate(rows)
        for column, cell in enumerate(line)
        if cell == START
    ]
    exits = [
        (row, column)
        for row, line in enumerate(rows)
        for column, cell in enumerate(line)
        if cell == EXIT
    ]
    if len(starts) != 1:
        raise MapError("the map has %d start cells where exactly one S is required" % len(starts))
    if len(exits) != 1:
        raise MapError("the map has %d exit cells where exactly one E is required" % len(exits))
    return rows, starts[0], exits[0]


def shortest(rows, start, end):
    """Return the move count on a shortest orthogonal path, or None.

    Breadth-first search: every edge costs one step, so the first time the exit
    is reached the distance is minimal (AMB-002). The start-equals-exit case
    returns 0 (no move is needed); the exit is only enqueued as a discovered
    cell so its own neighbours are never expanded.
    """
    if start == end:
        return 0
    height = len(rows)
    width = len(rows[0])
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        (row, column), distance = queue.popleft()
        for row_step, column_step in NEIGHBOURS:
            next_row = row + row_step
            next_column = column + column_step
            if not (0 <= next_row < height and 0 <= next_column < width):
                continue
            if (next_row, next_column) in seen:
                continue
            if rows[next_row][next_column] == WALL:
                continue
            if (next_row, next_column) == end:
                return distance + 1
            seen.add((next_row, next_column))
            queue.append(((next_row, next_column), distance + 1))
    return None


def main(argv):
    """Run the declared entry point: argv is sys.argv (program name first)."""
    if len(argv) != 2:
        sys.stderr.write("usage: bash pathfind.sh <mapfile>\n")
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
            text = handle.read()
    except OSError as exc:
        sys.stderr.write("pathfind.sh: cannot read %s: %s\n" % (path, exc))
        return 1

    try:
        rows, start, end = parse(text)
    except MapError as exc:
        sys.stderr.write("pathfind.sh: %s: %s\n" % (path, exc))
        return 1

    distance = shortest(rows, start, end)
    if distance is None:
        # The unreachable answer is the bare lowercase word.
        sys.stdout.write("unreachable\n")
    else:
        # The reachable answer is the bare integer, no label or unit.
        sys.stdout.write("%d\n" % distance)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
