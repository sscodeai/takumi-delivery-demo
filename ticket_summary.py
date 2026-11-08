#!/usr/bin/env python3
"""ticket-summary.py -- open/closed support-ticket counts per assignee.

Contract (docs/requirements/intake.yaml, deliverable block):

    run:           bash ticket-summary.sh {csv}
    assignee line: <assignee> <open> <closed>
    total line:    TOTAL <open-sum> <closed-sum>

The first CSV line is a header naming the columns; ``assignee`` and ``status``
are located by name, so their order and any extra columns do not matter.  Every
usable data row is one ticket.  For each assignee that appears in at least one
usable row exactly one line is printed, in ascending byte order of the assignee
string, followed by exactly one ``TOTAL`` line.  Rows that cannot be used are
skipped, counted, and reported in one diagnostic line on stderr.

The decisions this delivery settled are marked with greppable ``AMB-nnn``
comments next to the code that enacts them; docs/decisions.md lists them with
file:line anchors.
"""

from __future__ import annotations

import csv
import sys

OPEN = "open"
CLOSED = "closed"
REQUIRED = ("assignee", "status")

USAGE = "usage: bash ticket-summary.sh <csv>"


class UsageError(Exception):
    """The input cannot be used at all (unreadable file, missing header column)."""


def resolve_columns(header):
    """Return ``(assignee_index, status_index)`` for a header row.

    Names are matched after trimming surrounding whitespace and folding case,
    so ``Assignee`` and `` STATUS `` resolve to the same columns.  The first
    occurrence of a duplicated name wins.  A header without both required names
    is a usage error.
    """
    positions = {}
    for index, cell in enumerate(header):
        name = cell.strip().casefold()
        if name and name not in positions:
            positions[name] = index
    missing = [name for name in REQUIRED if name not in positions]
    if missing:
        plural = "s" if len(missing) > 1 else ""
        raise UsageError(
            "missing required column%s: %s" % (plural, ", ".join(missing))
        )
    return positions["assignee"], positions["status"]


# AMB-001 (strict): only case-insensitive `open` and `closed` are recognised;
# every other status makes the row unusable instead of counting as open.
def classify_status(value):
    """Return ``"open"``, ``"closed"`` or ``None`` for an unusable status."""
    status = value.strip().casefold()
    if status == OPEN:
        return "open"
    if status == CLOSED:
        return "closed"
    return None


def read_records(path):
    """Read every CSV record from *path* (RFC 4180 quoting honoured)."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            # AMB-005 (quoted-aware): the stdlib RFC 4180 reader keeps commas and
            # doubled quotes inside a quoted field instead of splitting on them.
            return list(csv.reader(handle))
    except OSError as exc:
        raise UsageError("cannot read %s: %s" % (path, exc.strerror or exc))
    except UnicodeDecodeError as exc:
        raise UsageError("cannot decode %s as UTF-8: %s" % (path, exc.reason))
    except csv.Error as exc:
        raise UsageError("malformed CSV in %s: %s" % (path, exc))


def summarise(records):
    """Count open/closed rows per assignee; return ``(counts, skipped)``.

    ``counts`` maps the trimmed assignee spelling to ``[open, closed]``.
    ``skipped`` is the number of unusable data rows (REQ-006).
    """
    if not records:
        raise UsageError("empty input: no header row")

    assignee_index, status_index = resolve_columns(records[0])
    width = len(records[0])
    counts = {}
    skipped = 0

    for record in records[1:]:
        # AMB-002 (skip-count): a row with the wrong number of fields is
        # unusable -- it is counted as skipped and contributes to nothing.
        if len(record) != width:
            skipped += 1
            continue
        assignee = record[assignee_index].strip()
        status = record[status_index].strip()
        kind = classify_status(status)
        if not assignee or not status or kind is None:
            # AMB-002 (skip-count): an empty assignee, an empty status or an
            # unrecognised status also makes the row unusable and skippable.
            skipped += 1
            continue
        # AMB-003 (case-sensitive): the trimmed spelling is the grouping key, so
        # `Alice` and `alice` remain two assignees with their own spelling.
        # AMB-004 (count-each-row): every usable data row adds one ticket, so
        # two identical rows count twice.
        bucket = counts.setdefault(assignee, [0, 0])
        bucket[0 if kind == "open" else 1] += 1

    return counts, skipped


def ordered_assignees(counts):
    """Assignee keys in ascending locale-independent byte order (REQ-003)."""
    return sorted(counts, key=lambda name: name.encode("utf-8"))


def render(counts):
    """Return the report lines: one per assignee, then exactly one TOTAL."""
    lines = []
    open_total = 0
    closed_total = 0
    for assignee in ordered_assignees(counts):
        open_count, closed_count = counts[assignee]
        lines.append("%s %d %d" % (assignee, open_count, closed_count))
        open_total += open_count
        closed_total += closed_count
    lines.append("TOTAL %d %d" % (open_total, closed_total))
    return lines


def main(argv):
    if len(argv) != 2:
        sys.stderr.write(USAGE + "\n")
        return 2

    try:
        records = read_records(argv[1])
        counts, skipped = summarise(records)
    except UsageError as exc:
        sys.stderr.write("ticket-summary: %s\n" % exc)
        return 2

    sys.stdout.write("\n".join(render(counts)) + "\n")
    sys.stdout.flush()

    # AMB-002 (skip-count): one stderr diagnostic states how many rows were
    # skipped and the tool still exits 0; stdout stays limited to the report.
    sys.stderr.write(
        "skipped %d %s\n" % (skipped, "row" if skipped == 1 else "rows")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
