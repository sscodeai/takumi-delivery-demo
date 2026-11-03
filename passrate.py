#!/usr/bin/env python3
"""Implementation behind ``bash passrate.sh <csv>``.

The confirmed requirement document is ``docs/requirements/intake.yaml``. Its
deliverable block declares::

    run:          bash passrate.sh {csv}
    suite line:   <suite> <passed> <total> <pct>
    total line:   TOTAL <passed_sum> <total_sum>
    skipped line: SKIPPED <skipped-count>

The input is a CSV of test-run records. Its first line normally names the
columns ``suite``, ``passed`` and ``total``; the tool resolves those columns by
header name, so column order and additional columns do not matter (REQ-003).
The deliverable's declared sample carries no header line, so a first line that
is a valid three-field data row (``suite,passed,total``) is accepted as data;
anything else on the first line must be a header naming the required columns,
and a header missing one of them is a fatal error.

Every distinct suite is printed once, summing all of its rows (AMB-002). A row
that cannot produce a percentage is skipped, excluded from every total and
counted on the final ``SKIPPED`` line (AMB-003). Percentages are exact rational
arithmetic rounded half away from zero to one decimal (AMB-001); binary
floating point is never used, so repeated runs are byte-identical.

The whole report is built before anything is written to stdout, so a fatal
input error never leaves partial report lines behind.
"""

import csv
import re
import sys

# The columns the report needs, matched case-insensitively after trimming
# surrounding blanks. The first CSV line names them in any order (REQ-003).
SUITE = "suite"
PASSED = "passed"
TOTAL = "total"
REQUIRED = (SUITE, PASSED, TOTAL)

# A count is a non-negative integer: plain digits, with an optional leading "+".
# Signs, decimals ("48.0"), blanks-only cells and text are not integers (REQ-006).
COUNT = re.compile(r"^\+?[0-9]+$")

# A record the csv parser itself rejected. It is one malformed row like any
# other: skipped, excluded from every aggregate and counted on SKIPPED.
MALFORMED = object()

# The order assumed when the input carries no header line (the declared sample).
DEFAULT_ORDER = (SUITE, PASSED, TOTAL)


class InputError(Exception):
    """The input cannot be read at all: bad header, missing file, bad encoding."""


def looks_like_header(record):
    """Return True when the first record must be read as a header line.

    A header names at least one of the required columns. A headerless data row
    (the declared sample) is a valid ``suite,passed,total`` triple, so it is
    data. Anything else -- the wrong width, a non-integer count, an unparsable
    record -- can only be a header, which then has to satisfy REQ-003.
    """
    if record is MALFORMED:
        return True
    names = [cell.strip().lower() for cell in record]
    if any(name in REQUIRED for name in names):
        return True
    if len(record) != len(DEFAULT_ORDER):
        return True
    return (
        parse_count(record[1]) is None
        or parse_count(record[2]) is None
    )


def resolve_columns(header):
    """Map each required column name to its index, or raise InputError (REQ-003).

    Names are compared case-insensitively after trimming surrounding blanks.
    Additional columns are ignored; the first occurrence of a repeated name
    wins. A header missing any required name is fatal, and the diagnostic names
    every missing column.
    """
    names = [cell.strip().lower().lstrip("\ufeff") for cell in header]
    positions = {}
    for index, name in enumerate(names):
        if name in REQUIRED and name not in positions:
            positions[name] = index
    missing = [name for name in REQUIRED if name not in positions]
    if missing:
        raise InputError(
            "missing required column(s): %s" % ", ".join(missing)
        )
    return positions


def parse_count(text):
    """Return the non-negative integer in a cell, or None when it is not one."""
    text = text.strip()
    if not COUNT.match(text):
        return None
    return int(text)


def parse_row(record, columns, width):
    """Return ``(suite, passed, total)`` for a counted row, or None when malformed.

    A row is malformed when its field count differs from the header width, when
    ``passed`` or ``total`` is not a non-negative integer, or when ``total`` is
    zero (REQ-006). The suite value is trimmed before grouping.
    """
    if record is MALFORMED:
        return None
    if len(record) != width:
        return None
    passed = parse_count(record[columns[PASSED]])
    total = parse_count(record[columns[TOTAL]])
    if passed is None or total is None:
        return None
    if total == 0:
        return None
    return record[columns[SUITE]].strip(), passed, total


def format_percentage(passed, total):
    """Render ``passed / total * 100`` with one decimal, half away from zero.

    The percentage is scaled by 10 into an exact integer division. ``total`` is
    a positive integer, so the quotient and remainder are exact; sending an
    exact half up is the AMB-001 decision. Both counts are non-negative, so
    "away from zero" is plain half-up here.
    """
    scaled, remainder = divmod(passed * 1000, total)
    # AMB-001 (half-up): an exact half rounds away from zero, so 6.25% prints
    # 6.3 and 96.05% prints 96.1. `>=` sends the half up; `>` is the truncate
    # behaviour this decision rejects.
    if remainder * 2 >= total:
        scaled += 1
    return "%d.%d" % (scaled // 10, scaled % 10)


def read_records(handle):
    """Yield every CSV record, turning a parser-level error into MALFORMED.

    A single pathological record must not abort the run: it becomes a malformed
    row, so the caller skips it and counts it (AMB-003).
    """
    # strict=True makes RFC 4180 violations (an unclosed quote, text after a
    # closing quote) a csv.Error, so they become malformed rows under AMB-003
    # instead of being silently accepted as data.
    reader = csv.reader(handle, strict=True)
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error:
            yield MALFORMED


def summarise(records):
    """Build the report lines from an iterable of CSV records.

    Raises ``InputError`` when the first record cannot name the required
    columns.
    """
    iterator = iter(records)
    try:
        first = next(iterator)
    except StopIteration:
        raise InputError("the file is empty, so it has no header") from None

    if looks_like_header(first):
        if first is MALFORMED:
            raise InputError("the first line is not a readable header")
        columns = resolve_columns(first)
        width = len(first)
        data = iterator
    else:
        # The declared sample has no header line: read it as suite,passed,total.
        columns = {name: index for index, name in enumerate(DEFAULT_ORDER)}
        width = len(DEFAULT_ORDER)
        data = _prepend(first, iterator)

    groups = {}  # trimmed suite -> [passed sum, total sum]
    passed_sum = 0
    total_sum = 0
    skipped = 0

    for record in data:
        parsed = parse_row(record, columns, width)
        if parsed is None:
            # AMB-003 (skip-count): a malformed row is skipped and excluded from
            # every aggregate, and the run reports it on the SKIPPED line instead
            # of aborting. One counter increment per malformed row.
            skipped += 1
            continue
        suite, passed, total = parsed
        group = groups.get(suite)
        if group is None:
            groups[suite] = [passed, total]
        else:
            # AMB-002 (merge): every row of a repeated suite counts, so its
            # passed and total are summed into the one line printed for it.
            group[0] += passed
            group[1] += total
        passed_sum += passed
        total_sum += total

    lines = []
    # One line per distinct suite, sorted by the UTF-8 bytes of the suite name
    # so the report does not depend on row order (REQ-002, REQ-005).
    for suite in sorted(groups, key=lambda name: name.encode("utf-8")):
        passed, total = groups[suite]
        # REL-001: the percentage is derived from the very counts printed here.
        lines.append(
            "%s %d %d %s" % (suite, passed, total, format_percentage(passed, total))
        )

    # REQ-004: exactly one totals line, after the suite lines, over every
    # counted row. The request asks for no overall percentage, so there is none.
    lines.append("TOTAL %d %d" % (passed_sum, total_sum))
    # REQ-006: the SKIPPED line is printed only when at least one row was
    # skipped, and it is the final line.
    if skipped:
        lines.append("SKIPPED %d" % skipped)
    return lines


def _prepend(head, iterator):
    """Yield ``head`` then everything from ``iterator``."""
    yield head
    for item in iterator:
        yield item


def main(argv):
    """Entry point used by ``passrate.sh``; returns the process exit status."""
    if len(argv) != 2:
        sys.stderr.write("usage: bash passrate.sh <csv>\n")
        return 2

    path = argv[1]
    # A record with a very long field is a malformed row, not a crash: lift the
    # parser limit and let the row be counted like any other malformed row.
    try:
        csv.field_size_limit(2**31 - 1)
    except (OverflowError, ValueError):  # pragma: no cover - defensive
        pass

    try:
        with open(path, "r", encoding="utf-8-sig", errors="strict", newline="") as handle:
            lines = summarise(read_records(handle))
    except InputError as exc:
        sys.stderr.write("passrate.sh: %s: %s\n" % (path, exc))
        return 1
    except UnicodeDecodeError as exc:
        sys.stderr.write("passrate.sh: cannot decode %s: %s\n" % (path, exc))
        return 1
    except OSError as exc:
        sys.stderr.write("passrate.sh: cannot read %s: %s\n" % (path, exc))
        return 1

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
