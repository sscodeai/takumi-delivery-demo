#!/usr/bin/env python3
"""Per-assignee open/closed ticket counts from an ``assignee,status`` CSV.

Usage: python3 summary.py <csv>

The CSV's first line is a header naming the ``assignee`` and ``status``
columns; every later row is one ticket.  The report has one line per
assignee (both counts, always) and one file-wide ``TOTAL`` line.

Only the Python 3 standard library is used, so the tool needs no network
access and no install step.  The input file is opened read-only.
"""

from __future__ import annotations

import csv
import sys
from typing import Dict, Iterable, List, Sequence, Tuple

OPEN = "open"
CLOSED = "closed"
TOTAL_LABEL = "TOTAL"
REQUIRED_COLUMNS = ("assignee", "status")


class InputError(Exception):
    """The input cannot be read as an ``assignee,status`` ticket CSV."""


def resolve_columns(header: Sequence[str]) -> Tuple[int, int]:
    """Return the (assignee, status) indices named by the header line."""
    positions: Dict[str, int] = {}
    for index, name in enumerate(header):
        positions.setdefault(name, index)
    missing = [name for name in REQUIRED_COLUMNS if name not in positions]
    if missing:
        raise InputError(
            "header is missing required column(s): " + ", ".join(missing)
        )
    return positions["assignee"], positions["status"]


def read_rows(path: str) -> List[Tuple[str, str]]:
    """Read every data row as an (assignee, status) pair.

    Rows that are too short to carry both named columns are dropped here.
    """
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise InputError(
                    f"{path} is empty; expected an assignee,status header"
                )
            assignee_index, status_index = resolve_columns(header)
            needed = max(assignee_index, status_index)
            rows: List[Tuple[str, str]] = []
            try:
                for record in reader:
                    # AMB-004 (skip): a row that does not carry both cells is ignored.
                    if len(record) <= needed:
                        continue  # AMB-004 (skip): too short, contributes to no count.
                    rows.append((record[assignee_index], record[status_index]))
            except csv.Error as exc:
                raise InputError(f"cannot parse {path}: {exc}") from exc
            return rows
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"cannot decode {path} as UTF-8: {exc}") from exc


def summarise(rows: Iterable[Tuple[str, str]]) -> Dict[str, List[int]]:
    """Count each assignee's open and closed tickets.

    The result maps an assignee to ``[open_count, closed_count]``.  An
    assignee that only ever appears in one status keeps the other slot at 0.
    """
    counts: Dict[str, List[int]] = {}
    for assignee, status in rows:
        # AMB-004 (skip): a row with an empty assignee is ignored entirely.
        if assignee == "":
            continue  # AMB-004 (skip): empty assignee, no count.
        # AMB-003 (exact): only the exact lowercase tokens are recognised; no
        # trimming and no case folding are applied to the status cell.
        if status == OPEN:
            slot = 0
        elif status == CLOSED:
            slot = 1
        else:
            continue  # AMB-004 (skip): unrecognised status, no count.
        counts.setdefault(assignee, [0, 0])[slot] += 1
    return counts


def format_report(counts: Dict[str, List[int]]) -> List[str]:
    """Render one line per assignee, then exactly one file-wide totals line."""
    lines: List[str] = []
    # AMB-002 (alphabetical): locale-independent ascending byte order.
    for assignee in sorted(counts, key=lambda name: name.encode("utf-8")):
        opened, closed = counts[assignee]
        # AMB-001 (one-line): one line per assignee carries both counts.
        # AMB-005 (explicit-zero): both counts are always printed, so the
        # category an assignee is missing prints as 0.
        lines.append(f"{assignee} {opened} {closed}")
    open_total = sum(pair[0] for pair in counts.values())
    closed_total = sum(pair[1] for pair in counts.values())
    lines.append(f"{TOTAL_LABEL} {open_total} {closed_total}")
    return lines


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: bash summary.sh <csv>", file=sys.stderr)
        return 2
    try:
        counts = summarise(read_rows(argv[1]))
    except InputError as exc:
        print(f"summary: {exc}", file=sys.stderr)
        return 1
    try:
        for line in format_report(counts):
            print(line)
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
