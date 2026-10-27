#!/usr/bin/env python3
"""Implementation behind ``bash summary.sh <csv>``.

The requirement document is ``docs/requirements/intake.yaml``. Its deliverable
contract is::

    run: bash summary.sh {csv}
    suite line: <suite> <passed> <total> <percentage>
    total line:  TOTAL <tests>

Input is a CSV of test-run records whose header names the columns ``suite``,
``passed`` and ``total``. Each distinct suite is reported once, in order of
first appearance, with the pass percentage in percentage points rounded to one
decimal place.

Everything is computed on exact rationals (``fractions.Fraction``), so the
percentage and its rounding never depend on binary floating point and never
depend on row order.
"""

import csv
import re
import sys
from fractions import Fraction

# The three column names the requirement document declares. They are matched
# case-insensitively after stripping surrounding blanks, so a header written as
# ``Total,Suite,Passed`` locates the same columns as ``suite,passed,total``.
HEADER_NAMES = ("suite", "passed", "total")

# The declared column order, used for a file that carries no header row (the
# document's own ``input_format.sample`` is written that way).
DEFAULT_COLUMNS = {"suite": 0, "passed": 1, "total": 2}

# A passed/total cell is numeric when it is a plain decimal with an optional
# sign. Exponents, thousands separators and blanks are not counts.
NUMERIC = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")


def locate_columns(first_row):
    """Return (column map, was_header) for the first CSV record.

    REQ-002: the first row is a header naming the columns, and the columns are
    located BY NAME so a reordered file yields the same report. A first row that
    does not name all three columns is not a header, and is read as data in the
    declared order instead.
    """
    names = [cell.strip().lower() for cell in first_row]
    if all(name in names for name in HEADER_NAMES):
        return {name: names.index(name) for name in HEADER_NAMES}, True
    return dict(DEFAULT_COLUMNS), False


def render_tenths(tenths):
    """Render a value measured in tenths with one decimal, half away from zero.

    ``tenths`` is an exact Fraction. Rounding is integer arithmetic on the
    numerator and denominator, so no binary floating point value is involved in
    the rendered digit.
    """
    numerator, denominator = tenths.numerator, tenths.denominator
    negative = numerator < 0
    if negative:
        numerator = -numerator
    whole, remainder = divmod(numerator, denominator)
    # AMB-001 (half-up): an exact half rounds AWAY FROM ZERO, so a percentage of
    # exactly 6.25 prints as 6.3. `>=` is what makes the half go up; `>` would
    # truncate every exact half and is the mutation AMB-001 forbids.
    if remainder * 2 >= denominator:
        whole += 1
    if whole == 0:
        return "0.0"  # normalise a negative zero
    return "%s%d.%d" % ("-" if negative else "", whole // 10, whole % 10)


def percentage(passed, total):
    """Pass percentage in points, one decimal place, half away from zero.

    REQ-004: the token is ``passed / total * 100`` in percentage points (0..100)
    and always carries exactly one digit after the decimal point. Multiplying by
    ten before rendering is what lands on the one-decimal boundary.
    """
    return render_tenths(passed * 1000 / total)


def render_count(value):
    """Render a count as an exact decimal without a needless trailing ``.0``.

    Counts are sums of the input cells, so they stay exact: an integer cell stays
    an integer and a decimal cell keeps exactly the digits it was written with.
    """
    if value.denominator == 1:
        return str(value.numerator)
    negative = value < 0
    numerator = abs(value.numerator)
    whole, remainder = divmod(numerator, value.denominator)
    digits = []
    while remainder and len(digits) < 24:
        remainder *= 10
        digits.append(str(remainder // value.denominator))
        remainder %= value.denominator
    return "%s%d.%s" % ("-" if negative else "", whole, "".join(digits))


def parse_row(row, columns):
    """Return (suite, passed, total) for a usable row, or None to skip it.

    AMB-003 (skip-silent): a row that cannot yield a percentage is dropped
    without a word -- no suite line, no counter line, still exit 0. That covers a
    short row, a non-numeric passed/total, a total of zero, a blank suite id and
    a negative count (which cannot express a 0..100 percentage).
    """
    width = max(columns.values()) + 1
    if len(row) < width:
        return None
    suite = row[columns["suite"]]
    passed_text = row[columns["passed"]]
    total_text = row[columns["total"]]
    if suite == "":
        return None
    if not NUMERIC.match(passed_text) or not NUMERIC.match(total_text):
        return None
    passed = Fraction(passed_text)
    total = Fraction(total_text)
    if total == 0:
        return None
    if passed < 0 or total < 0:
        return None
    return suite, passed, total


def summarise(records):
    """Build the report lines from an iterable of CSV records."""
    columns = dict(DEFAULT_COLUMNS)
    merged = {}  # suite -> [passed, total]; dict keeps first-appearance order
    header_pending = True

    for row in records:
        if row is None:  # a record the csv parser itself rejected
            continue
        if header_pending:
            header_pending = False
            columns, consumed = locate_columns(row)
            if consumed:
                continue  # the header is never itself a data row
        parsed = parse_row(row, columns)
        if parsed is None:
            continue
        suite, passed, total = parsed
        entry = merged.get(suite)
        if entry is None:
            merged[suite] = [passed, total]
        else:
            # AMB-002 (merge): a repeated suite is one line whose passed and total
            # are the sums over every occurrence, so each row still counts.
            entry[0] += passed
            entry[1] += total

    lines = []
    # REQ-003: exactly one line per distinct suite, in order of first appearance.
    for suite, (passed, total) in merged.items():
        lines.append(
            "%s %s %s %s"
            % (suite, render_count(passed), render_count(total), percentage(passed, total))
        )

    # REQ-005: TOTAL is the summed denominator of the printed suite lines.
    total_tests = Fraction(0)
    for passed, total in merged.values():
        total_tests += total
    lines.append("TOTAL %s" % render_count(total_tests))
    return lines


def read_records(handle):
    """Yield every CSV record, turning a parser-level error into a skipped row.

    A single pathological record must never abort the run (REQ-006/AMB-003), so a
    ``csv.Error`` yields ``None`` and the caller drops the row.
    """
    reader = csv.reader(handle)
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error:
            yield None


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: bash summary.sh <csv>\n")
        return 2

    path = argv[1]
    # A record with a very long field is a malformed row, not a crash: lift the
    # parser limit and let the row be skipped like any other unusable row.
    try:
        csv.field_size_limit(2**31 - 1)
    except (OverflowError, ValueError):  # pragma: no cover - defensive
        pass

    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            lines = summarise(read_records(handle))
    except OSError as exc:
        # An unreadable input is not a "row that cannot yield a percentage": the
        # report cannot be produced at all, so stop with a diagnostic and no
        # result lines on stdout.
        sys.stderr.write("summary.sh: cannot read %s: %s\n" % (path, exc))
        return 1

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
