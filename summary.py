#!/usr/bin/env python3
"""Per-suite pass percentage from a ``suite,passed,total`` CSV.

Usage: bash summary.sh <csv>

The report is::

    <suite> <passed> <total> <percentage>   one line per distinct suite
    TOTAL <passed_sum> <total_sum>          exactly once, after the suite lines

Suite lines follow the order in which each suite first appears in the input.
The percentage is ``passed / total * 100`` printed with exactly one decimal
place, rounded half away from zero (AMB-001).  Repeated suite names are merged
into one line (AMB-002), a suite whose total is zero prints ``0.0`` (AMB-003),
and a malformed record stops the run with a diagnostic naming its line
(AMB-004).

The input's first record is normally the header ``suite,passed,total``; it is
consumed and never printed.  The declared sample in the requirement document
carries no header line, so a first record that is not that header is treated
as data with the columns in the declared order.  Surrounding whitespace on a
field is ignored.

Only the Python 3 standard library is used: no install step, no network
access, and the input file is opened read-only.  The whole report is built
before anything is written to stdout, so a fatal input error never leaves
partial report lines behind.

The ambiguities settled for this delivery are marked with greppable
``AMB-nnn`` comments below and recorded in ``docs/decisions.md``.
"""

from __future__ import annotations

import csv
import re
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

HEADER_NAMES = ("suite", "passed", "total")
USAGE = "usage: bash summary.sh <csv>"
DEFAULT_ORDER = (0, 1, 2)

# A count is a non-negative integer: plain digits with an optional leading "+".
# Signs, decimals ("48.0"), blanks-only cells and text are not integers.
COUNT = re.compile(r"^\+?[0-9]+$")


class InputError(Exception):
    """A problem with the input that must stop the run with a diagnostic."""


def parse_count(text: str) -> Optional[int]:
    """Return the non-negative integer in a cell, or ``None`` when it is not one."""
    text = text.strip()
    if not COUNT.match(text):
        return None
    return int(text)


def header_order(row: Sequence[str]) -> Optional[Tuple[int, int, int]]:
    """Return the column positions named by a header row, or ``None``.

    The declared header is exactly ``suite,passed,total``.  Names are matched
    case-insensitively after trimming blanks, and a header that names the same
    three columns in another order is accepted so the column order is not
    silently guessed.
    """
    names = [cell.strip().casefold().lstrip("\ufeff") for cell in row]
    if len(names) != len(HEADER_NAMES) or set(names) != set(HEADER_NAMES):
        return None
    return tuple(names.index(name) for name in HEADER_NAMES)  # type: ignore[return-value]


def record_from_row(row: Sequence[str]) -> str:
    """Render a CSV record for an error message without hiding its shape."""
    return ",".join(row)


def parse_row(
    row: Sequence[str], columns: Sequence[int], line_no: int
) -> Tuple[str, int, int]:
    """Return ``(suite, passed, total)`` or raise ``InputError`` naming the line.

    AMB-004 (stop-error): a row with the wrong number of fields, a non-integer
    or negative count, or ``passed`` greater than ``total`` is fatal.  The
    diagnostic names the offending input line and the run stops; no report is
    printed.
    """
    record = record_from_row(row)

    # AMB-004 (stop-error): any unusable record stops the run and names its line.
    if len(row) != len(HEADER_NAMES):
        raise InputError(
            "line %d: malformed record %r: expected %d fields, found %d"
            % (line_no, record, len(HEADER_NAMES), len(row))
        )

    suite = row[columns[0]].strip()
    passed_text = row[columns[1]].strip()
    total_text = row[columns[2]].strip()

    passed = parse_count(passed_text)
    if passed is None:
        raise InputError(
            "line %d: malformed record %r: passed is not a non-negative integer: %r"
            % (line_no, record, passed_text)
        )

    total = parse_count(total_text)
    if total is None:
        raise InputError(
            "line %d: malformed record %r: total is not a non-negative integer: %r"
            % (line_no, record, total_text)
        )

    if passed > total:
        raise InputError(
            "line %d: malformed record %r: passed (%d) is greater than total (%d)"
            % (line_no, record, passed, total)
        )

    return suite, passed, total


def read_records(path: str) -> List[Tuple[int, List[str]]]:
    """Read every non-blank CSV record as ``(starting line number, fields)``.

    Blank lines carry no record.  A parser-level failure (for example an
    unclosed quote) is a malformed input and becomes an ``InputError``.
    """
    records: List[Tuple[int, List[str]]] = []
    try:
        handle = open(path, "r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError("cannot read %s: %s" % (path, exc.strerror or exc)) from exc

    with handle:
        reader = csv.reader(handle)
        previous_line = 0
        try:
            for row in reader:
                start_line = previous_line + 1
                previous_line = reader.line_num
                if not row or (len(row) == 1 and not row[0].strip()):
                    continue
                records.append((start_line, row))
        except (csv.Error, UnicodeDecodeError) as exc:
            raise InputError(
                "line %d: malformed CSV record: %s" % (previous_line + 1, exc)
            ) from exc
    return records


def format_percentage(passed: int, total: int) -> str:
    """Render ``passed / total * 100`` with exactly one decimal place.

    The value is scaled by 10 so the division stays exact integer arithmetic.
    AMB-001 (half-up): an exact half rounds away from zero, so 2/3 prints
    ``66.7`` (not ``66.6``) and 1/16 prints ``6.3``.  Both counts are
    non-negative, so "away from zero" is plain half-up here.
    """
    # AMB-003 (zero-rate): a suite whose total is zero prints a line with 0.0.
    if total == 0:
        return "0.0"

    scaled, remainder = divmod(passed * 1000, total)
    # AMB-001 (half-up): `>=` sends an exact half up; `>` would be truncation.
    if remainder * 2 >= total:
        scaled += 1
    return "%d.%d" % (scaled // 10, scaled % 10)


def build_report(records: Iterable[Tuple[int, List[str]]]) -> str:
    """Build the complete report text (suite lines then one TOTAL line)."""
    order: List[str] = []
    totals: Dict[str, List[int]] = {}
    columns: Sequence[int] = DEFAULT_ORDER
    first = True

    for line_no, row in records:
        if first:
            first = False
            found = header_order(row)
            if found is not None:
                columns = found
                continue
            # The declared sample has no header line: the first record is data
            # in the declared column order.
            columns = DEFAULT_ORDER

        suite, passed, total = parse_row(row, columns, line_no)

        # AMB-002 (merge): every row for a name is added to that suite, and the
        # suite keeps the position where it first appeared.
        if suite in totals:
            totals[suite][0] += passed
            totals[suite][1] += total
        else:
            order.append(suite)
            totals[suite] = [passed, total]

    lines: List[str] = []
    passed_sum = 0
    total_sum = 0
    for suite in order:
        passed, total = totals[suite]
        passed_sum += passed
        total_sum += total
        lines.append(
            "%s %d %d %s" % (suite, passed, total, format_percentage(passed, total))
        )
    lines.append("TOTAL %d %d" % (passed_sum, total_sum))
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print(USAGE, file=sys.stderr)
        return 2

    path = argv[1]
    try:
        report = build_report(read_records(path))
    except InputError as exc:
        print("summary.sh: %s" % exc, file=sys.stderr)
        return 1

    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
