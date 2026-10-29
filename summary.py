#!/usr/bin/env python3
"""Implementation behind ``bash summary.sh <csv>``.

The confirmed requirement document is ``docs/requirements/intake.yaml``. Its
deliverable block declares::

    run:          bash summary.sh {csv}
    region line:  <region> <count> <sum> <mean>
    total line:   TOTAL <count> <sum>
    skipped line: SKIPPED <skipped-count>

The input is a CSV whose first line is the header ``region,amount`` (matched
case-insensitively after trimming surrounding blanks). Accepted records are
grouped by the trimmed region string; each region is printed once, sorted by
the UTF-8 bytes of its name, with the group's count, exact sum and mean. Money
is printed with exactly two decimal places, rounded half away from zero
(AMB-003).

All arithmetic runs on ``fractions.Fraction``: exact rational values, never
binary floating point, so every printed digit is reproducible. The file is
read completely and the report is built before anything is written to stdout,
so a fatal input error never leaves partial report lines behind.
"""

import csv
import re
import sys
from fractions import Fraction

# The declared header: exactly these two columns, in this order (REQ-002).
HEADER = ("region", "amount")

# An amount is a plain decimal: optional sign, digits, optional fractional part.
# Currency symbols, thousands separators and exponent notation are not amounts
# (REQ-005).
AMOUNT = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")

# A record the csv parser itself rejected. It is one malformed row like any
# other: skipped, excluded from every aggregate and counted on SKIPPED.
MALFORMED = object()


class HeaderError(Exception):
    """The input does not start with the declared ``region,amount`` header."""


def locate_header(record):
    """Validate the first record and return nothing (REQ-002).

    The header must name exactly ``region`` and ``amount`` in that order.
    Names are compared case-insensitively after trimming surrounding blanks.
    A missing, unparsable or different header is fatal, so the caller prints no
    report lines and exits non-zero.
    """
    if record is MALFORMED:
        raise HeaderError("the first line is not a readable header")
    cells = [cell.strip().lower() for cell in record]
    if tuple(cells) != HEADER:
        raise HeaderError(
            "expected the header 'region,amount', found %r" % (record,)
        )


def parse_amount(text):
    """Return the exact amount for a cell, or None when it is not a plain decimal.

    ``Fraction`` keeps the decimal value exact, so later sums, means and
    half-up rounding never depend on binary floating point (REQ-007).
    """
    if not AMOUNT.match(text):
        return None
    return Fraction(text)


def parse_row(record):
    """Return ``(region, amount)`` for an accepted row, or None when malformed.

    A row is malformed when it has a field count other than two, when its region
    is empty after trimming, or when its amount is not a plain decimal (REQ-005).
    """
    if record is MALFORMED:
        return None
    if len(record) != 2:
        return None
    region = record[0].strip()
    if region == "":
        return None
    amount = parse_amount(record[1])
    if amount is None:
        return None
    return region, amount


def format_money(value):
    """Render a value as money: exactly two decimals, half away from zero.

    ``value`` is an exact ``Fraction``. Scaling by 100 and rounding the scaled
    integer with integer arithmetic is what puts the rounding boundary exactly
    where the printed digit is, with no binary floating point involved.
    """
    scaled = value * 100
    numerator, denominator = scaled.numerator, scaled.denominator
    negative = numerator < 0
    numerator = -numerator if negative else numerator
    whole, remainder = divmod(numerator, denominator)
    # AMB-003 (half-up): an exact half rounds AWAY FROM ZERO, so 1.005 prints as
    # 1.01 and -1.005 prints as -1.01. `>=` is what sends the half up; `>` is
    # the truncate behaviour this decision rejects.
    if remainder * 2 >= denominator:
        whole += 1
    if whole == 0:
        negative = False  # never print a negative zero
    return "%s%d.%02d" % ("-" if negative else "", whole // 100, whole % 100)


def read_records(handle):
    """Yield every CSV record, turning a parser-level error into MALFORMED.

    A single pathological record must not abort the run: it is a malformed row,
    so the caller skips it and counts it (AMB-001).
    """
    # strict=True makes RFC 4180 violations (an unclosed quote, text after a
    # closing quote) a csv.Error, so they become malformed rows under AMB-001
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
    """Build the report lines from an iterable of CSV records (header first).

    Raises ``HeaderError`` when the first record is not the declared header.
    """
    iterator = iter(records)
    try:
        first = next(iterator)
    except StopIteration:
        raise HeaderError("the file is empty, so it has no header") from None
    locate_header(first)

    groups = {}  # trimmed region -> [accepted row count, exact sum]
    accepted = 0
    skipped = 0

    for record in iterator:
        parsed = parse_row(record)
        if parsed is None:
            # AMB-001 (skip-count): a malformed row is skipped and excluded from
            # every aggregate, and the run reports it on the SKIPPED line instead
            # of aborting. One counter increment per malformed record.
            skipped += 1
            continue
        region, amount = parsed
        group = groups.get(region)
        if group is None:
            groups[region] = [1, amount]
        else:
            # AMB-002 (merge): identical rows are independent orders, so every
            # occurrence counts again -- the row count grows and the sum adds the
            # amount; nothing is de-duplicated.
            group[0] += 1
            group[1] += amount
        accepted += 1

    lines = []
    total = Fraction(0)
    # REQ-003: one line per distinct trimmed region, ascending by the UTF-8
    # bytes of the region string, which also makes the report row-order
    # independent (REQ-009).
    for region in sorted(groups, key=lambda name: name.encode("utf-8")):
        count, amount = groups[region]
        lines.append(
            "%s %d %s %s"
            % (region, count, format_money(amount), format_money(amount / count))
        )
        total += amount

    # REQ-004: exactly one totals line, always printed, over every accepted row.
    lines.append("TOTAL %d %s" % (accepted, format_money(total)))
    # REQ-005: exactly one SKIPPED line, after the TOTAL line, always printed.
    lines.append("SKIPPED %d" % skipped)
    return lines


def main(argv):
    """Entry point used by ``summary.sh``; returns the process exit status."""
    if len(argv) != 2:
        sys.stderr.write("usage: bash summary.sh <csv>\n")
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
    except HeaderError as exc:
        sys.stderr.write("summary.sh: %s: %s\n" % (path, exc))
        return 1
    except UnicodeDecodeError as exc:
        sys.stderr.write("summary.sh: cannot decode %s: %s\n" % (path, exc))
        return 1
    except OSError as exc:
        sys.stderr.write("summary.sh: cannot read %s: %s\n" % (path, exc))
        return 1

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
