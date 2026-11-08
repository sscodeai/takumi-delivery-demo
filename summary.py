#!/usr/bin/env python3
"""Per-assignee open/closed ticket counts from an ``assignee,status`` CSV.

Usage: bash summary.sh <csv>

The first line of the input is a header that must name the columns
``assignee`` and ``status``; columns are located by name, so their order and
any extra columns do not matter.  Fields follow RFC 4180 quoting (commas,
doubled quotes and embedded newlines inside quoted fields) and records end
with LF or CRLF.

The report is exactly one line per assignee, ``<assignee> <open> <closed>``,
sorted by the UTF-8 bytes of the assignee name.  Malformed rows are skipped
and their number is reported on standard error; the run still exits 0.  Only
the Python 3 standard library is used, so no install step or network access is
needed, and the input file is opened read-only.
"""

from __future__ import annotations

import csv
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

OPEN = "open"
CLOSED = "closed"
REQUIRED_COLUMNS = ("assignee", "status")


class InputError(Exception):
    """The input cannot be read as an ``assignee,status`` ticket CSV."""


def _header_name(cell: str) -> str:
    """Normalise a header cell: drop a BOM, surrounding blanks and case."""
    return cell.strip().lstrip("\ufeff").lower()


def resolve_columns(header: Sequence[str]) -> Tuple[int, int]:
    """Return the (assignee, status) indices named by the header line."""
    positions: Dict[str, int] = {}
    for index, cell in enumerate(header):
        positions.setdefault(_header_name(cell), index)
    missing = [name for name in REQUIRED_COLUMNS if name not in positions]
    # AMB-003 (skip-count): a header without `assignee` and `status` stops the
    # run with a clear stderr message and a nonzero exit instead of guessing
    # column positions.
    if missing:
        raise InputError(
            "header is missing required column(s): " + ", ".join(missing)
        )
    return positions["assignee"], positions["status"]


def normalise_assignee(value: str) -> str:
    """Trim surrounding whitespace and keep the case of an assignee name."""
    # AMB-004 (trim-case-sensitive): trim only, so `Alice` and `alice` remain
    # two distinct assignees with two separate lines.
    return value.strip()


def classify_status(value: str) -> Optional[str]:
    """Return ``open``/``closed`` for a recognised status, otherwise None."""
    # AMB-001 (exact-match): trim and compare case-insensitively against the
    # two recognised tokens; any other status is not counted.
    cleaned = value.strip().lower()
    if cleaned == OPEN:
        return OPEN
    if cleaned == CLOSED:
        return CLOSED
    return None


def summarise_records(
    header: Sequence[str], records: Iterable[Sequence[str]]
) -> Tuple[Dict[str, List[int]], int]:
    """Count each assignee's open/closed tickets and the skipped row count."""
    assignee_index, status_index = resolve_columns(header)
    needed = max(assignee_index, status_index)
    counts: Dict[str, List[int]] = {}
    skipped = 0
    for record in records:
        # AMB-003 (skip-count): a row too short to carry both named columns is
        # skipped and counted, and the run continues.
        if len(record) <= needed:
            skipped += 1
            continue
        assignee = normalise_assignee(record[assignee_index])
        # AMB-003 (skip-count): an empty assignee cell is skipped and counted.
        if assignee == "":
            skipped += 1
            continue
        status = classify_status(record[status_index])
        # AMB-003 (skip-count): an empty or unrecognised status is skipped and
        # counted rather than being assigned to either bucket.
        if status is None:
            skipped += 1
            continue
        slot = 0 if status == OPEN else 1
        counts.setdefault(assignee, [0, 0])[slot] += 1
    return counts, skipped


def summarise_file(path: str) -> Tuple[Dict[str, List[int]], int]:
    """Read ``path`` as a ticket CSV and return its counts and skip count."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise InputError(
                    f"{path} is empty; expected a header naming "
                    + ", ".join(REQUIRED_COLUMNS)
                )
            return summarise_records(header, reader)
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"cannot decode {path} as UTF-8: {exc}") from exc
    except csv.Error as exc:
        raise InputError(f"cannot parse {path} as CSV: {exc}") from exc


def format_report(counts: Dict[str, List[int]]) -> List[str]:
    """Render one ``<assignee> <open> <closed>`` line per assignee."""
    lines: List[str] = []
    # REQ-004: sort by the UTF-8 bytes of the name, independent of the locale
    # and of the input row order.
    for assignee in sorted(counts, key=lambda name: name.encode("utf-8")):
        opened, closed = counts[assignee]
        # AMB-002 (one-line-per-assignee): one line per assignee carries both
        # counts; there is no per-status line and no extra summary line.
        lines.append(f"{assignee} {opened} {closed}")
    return lines


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: bash summary.sh <csv>\n")
        return 2
    try:
        counts, skipped = summarise_file(argv[1])
    except InputError as exc:
        sys.stderr.write(f"summary: {exc}\n")
        return 1
    # AMB-001 / AMB-003 (skip-count): rows excluded for an empty field or an
    # unrecognised status are reported on stderr, never on stdout.
    if skipped:
        sys.stderr.write(f"summary: skipped {skipped} malformed row(s)\n")
    report = "".join(line + "\n" for line in format_report(counts))
    try:
        # Write UTF-8 bytes directly so the output does not depend on the
        # process locale (REQ-004).
        sys.stdout.buffer.write(report.encode("utf-8"))
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
