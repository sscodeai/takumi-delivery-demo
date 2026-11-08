#!/usr/bin/env python3
"""Implementation behind ``bash summary.sh <csv>``.

Contract: ``docs/requirements/intake.yaml``.

The input is a CSV whose first line is a header naming the columns ``region``
and ``amount``. Columns are mapped by header name, so their order in the file
does not matter (REQ-002). Data rows are comma separated and must supply one
value per header column; a row with any other field count is malformed.

Output, in this order:

    <region> <revenue> <average_order_value>     one line per region
    SKIPPED <skipped>                            always, even when zero
    TOTAL <revenue> <orders>                     always, exactly once

Revenue and average are printed with exactly two decimals, rounded half away
from zero from exact arithmetic (AMB-003). The group key is the region cell
trimmed of surrounding ASCII whitespace and compared case-sensitively
(AMB-004). Every valid row counts as its own sales record, so duplicates are
merged, never deduplicated (AMB-002). A row that cannot be read is skipped,
excluded from every aggregate, and counted on the SKIPPED line (AMB-001).
"""

import csv
import re
import sys
from decimal import Decimal, InvalidOperation
from fractions import Fraction

REGION_COLUMN = "region"
AMOUNT_COLUMN = "amount"

# Surrounding ASCII whitespace trimmed from a region cell (AMB-004).
ASCII_WHITESPACE = " \t\r\n\f\v"

# A "plain decimal number": optional sign, then digits with an optional
# fractional part (or a bare fraction such as ".5"). No thousands separators,
# currency symbols, percent signs, exponents or surrounding blanks.
AMOUNT_RE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")

# A record the csv parser itself rejected. It is a malformed data row like any
# other: skipped, excluded from every aggregate and counted on SKIPPED.
MALFORMED = object()

USAGE = "usage: bash summary.sh <csv>\n"


class InputError(Exception):
    """The file cannot be used as input at all (empty, or no valid header)."""


def read_records(handle):
    """Yield every CSV record, turning a parser-level error into MALFORMED.

    One pathological record must not abort the run: it becomes a malformed row,
    so the caller skips it and counts it (AMB-001).
    """
    reader = csv.reader(handle, strict=True)
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error:
            yield MALFORMED


def header_columns(record):
    """Return ``(width, region_index, amount_index)`` for the header row.

    The header names are matched after trimming surrounding ASCII whitespace and
    folding ASCII case, so ``Region,Amount`` is still the declared header. A
    header that does not name both required columns is a fatal input error.
    """
    if record is MALFORMED:
        raise InputError("cannot parse the header row")
    names = [field.strip(ASCII_WHITESPACE).lower() for field in record]
    region_index = amount_index = None
    for index, name in enumerate(names):
        if name == REGION_COLUMN and region_index is None:
            region_index = index
        elif name == AMOUNT_COLUMN and amount_index is None:
            amount_index = index
    missing = [
        name
        for name, index in (
            (REGION_COLUMN, region_index),
            (AMOUNT_COLUMN, amount_index),
        )
        if index is None
    ]
    if missing:
        raise InputError(
            "header does not name required column(s): %s" % ", ".join(missing)
        )
    return len(record), region_index, amount_index


def parse_region(text):
    """Return the trimmed region key, or None when the cell is blank.

    AMB-004 (exact-trimmed): surrounding ASCII whitespace is removed and case is
    preserved, so ``north`` and ``North`` are two different regions.
    """
    region = text.strip(ASCII_WHITESPACE)
    return region if region else None


def parse_amount(text):
    """Return the exact value of an amount cell, or None when it is malformed.

    Only a plain decimal is accepted. The value is kept as an exact
    ``Fraction`` so sums never accumulate binary floating-point error.
    """
    if not AMOUNT_RE.match(text):
        return None
    try:
        return Fraction(Decimal(text))
    except (InvalidOperation, ValueError):  # defensive: the regex fixes the shape
        return None


def round_cents(value):
    """Round an exact value to integer cents, half away from zero.

    AMB-003 (half-up): an exact half goes away from zero. The comparison uses
    the exact remainder, never a binary approximation.
    """
    sign = -1 if value < 0 else 1
    magnitude = abs(value)
    numerator = magnitude.numerator * 100
    denominator = magnitude.denominator
    whole, remainder = divmod(numerator, denominator)
    # AMB-003 (half-up): `>=` sends an exact half away from zero; `>` would be
    # the truncate behaviour this decision rejects.
    if remainder * 2 >= denominator:
        whole += 1
    return sign * whole


def format_cents(cents):
    """Render integer cents with exactly two decimals and no grouping."""
    sign = "-" if cents < 0 else ""
    magnitude = abs(cents)
    return "%s%d.%02d" % (sign, magnitude // 100, magnitude % 100)


def format_value(value):
    """Render an exact value with two decimals, half away from zero (AMB-003)."""
    return format_cents(round_cents(value))


def summarise(records):
    """Build the report lines from an iterable of CSV records."""
    iterator = iter(records)
    try:
        first = next(iterator)
    except StopIteration:
        # REQ-012: an empty file is unusable, not an empty report.
        raise InputError("empty file: no header row")

    width, region_index, amount_index = header_columns(first)

    groups = {}  # trimmed region -> [count, exact Fraction sum]
    skipped = 0

    for record in iterator:
        # AMB-001 (skip-count): malformed = unparsable record, wrong field
        # count, blank region, or a non-decimal amount. Each such row is
        # skipped once, excluded from every aggregate, and counted.
        if record is MALFORMED or len(record) != width:
            skipped += 1
            continue

        region = parse_region(record[region_index])
        if region is None:
            # AMB-001 (skip-count): a blank region cell makes the row malformed.
            skipped += 1
            continue

        amount = parse_amount(record[amount_index])
        if amount is None:
            # AMB-001 (skip-count): a non-decimal amount makes the row malformed.
            # AMB-003 (half-up): negative and zero amounts are valid measures,
            # they are not malformed; this branch only rejects unreadable text.
            skipped += 1
            continue

        group = groups.get(region)
        if group is None:
            groups[region] = [1, amount]
        else:
            # AMB-002 (merge): every occurrence is its own sales record; all
            # rows of one region accumulate into its single aggregate line.
            group[0] += 1
            group[1] += amount

    lines = []
    total_orders = 0
    total_cents = 0

    # REQ-011: region lines in ascending byte order of the region name, so the
    # report depends only on the multiset of valid rows.
    for region in sorted(groups, key=lambda name: name.encode("utf-8")):
        orders, raw_sum = groups[region]
        # REQ-003 / AMB-003: revenue is the region's rounded raw sum; the mean
        # divides the UNROUNDED sum by the count and is rounded only for output.
        revenue_cents = round_cents(raw_sum)
        average_cents = round_cents(Fraction(raw_sum, orders))
        # AMB-004 (exact-trimmed): the printed id is the trimmed, case-exact key.
        lines.append(
            "%s %s %s"
            % (region, format_cents(revenue_cents), format_cents(average_cents))
        )
        total_orders += orders
        # REL-002 (additivity): the printed total is the sum of the printed
        # per-region revenues, so the report always adds up exactly.
        total_cents += revenue_cents

    # AMB-001 (skip-count): one line carrying the number of skipped rows,
    # printed even when it is zero (REQ-005). It follows the region lines.
    lines.append("SKIPPED %d" % skipped)
    # REQ-004: exactly one totals line, after the SKIPPED line. With no valid
    # rows this is "TOTAL 0.00 0".
    lines.append("TOTAL %s %d" % (format_cents(total_cents), total_orders))
    return lines


def main(argv):
    """Entry point used by ``summary.sh``; returns the process exit status."""
    if len(argv) != 2:
        sys.stderr.write(USAGE)
        return 2

    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            lines = summarise(read_records(handle))
    except InputError as exc:
        sys.stderr.write("summary.sh: %s: %s\n" % (path, exc))
        return 1
    except OSError as exc:
        sys.stderr.write(
            "summary.sh: cannot read %s: %s\n" % (path, exc.strerror or exc)
        )
        return 1
    except UnicodeDecodeError:
        sys.stderr.write("summary.sh: %s is not valid UTF-8 text\n" % path)
        return 1

    # REQ-012: stdout carries report lines only; fatal input errors never leave
    # a partial report behind because the whole report is built first.
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
