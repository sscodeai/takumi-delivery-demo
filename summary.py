#!/usr/bin/env python3
"""Implementation behind ``bash summary.sh <csv>``.

The confirmed requirement document is ``docs/requirements/intake.yaml``. Its
deliverable block declares::

    run:          bash summary.sh {csv}
    region line:  <region> <count> <sum> <mean>
    total line:   TOTAL <count> <sum>
    skipped line: SKIPPED <skipped-count>

The input is a CSV of sales records whose first line is the header
``region,amount`` (matched case-insensitively after trimming surrounding
blanks). The requirement document's declared sample carries no header line, so
a first line that is not that header is read as data instead of being dropped;
a file that does carry the header never counts it as a data row (REQ-001).

Each distinct region is printed once, with every row of that region merged into
its count, sum and mean (AMB-002). Rows that cannot be used are skipped,
excluded from every aggregate and reported on the final ``SKIPPED`` line only
when at least one was skipped (AMB-001, REQ-004). All arithmetic is exact
(``fractions.Fraction``) and printed values are rounded half away from zero at
the second decimal place (AMB-003, REQ-006); binary floating point is never
used, so repeated runs print byte-identical output.

The whole report is built before anything is written to stdout, so a fatal
input error never leaves partial report lines behind.
"""

import csv
import re
import sys
from decimal import Decimal, InvalidOperation
from fractions import Fraction

# The two columns named by the header, in the only order the deliverable
# assigns them: region is field 0, amount is field 1 (REQ-001, REQ-002).
COLUMNS = ("region", "amount")

# AMB-004 (plain-decimal): an amount is an optional leading sign, digits and an
# optional fractional part -- nothing else. Currency symbols, thousands
# separators, percent signs and surrounding blanks are NOT stripped, so a row
# carrying them is unusable under AMB-001.
AMOUNT = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")

# A record the csv parser itself rejected. It is one unusable row like any
# other: skipped, excluded from every aggregate and counted on SKIPPED.
MALFORMED = object()

USAGE = "usage: bash summary.sh <csv>\n"


class InputError(Exception):
    """The input cannot be read at all: missing file, unreadable path, bad encoding."""


def looks_like_header(record):
    """Return True when the first record is the declared header row.

    The declared header is ``region,amount``; REQ-001 says the same line is
    still a header when its names differ in case or surrounding whitespace, so
    each field is trimmed and lowercased before comparison. Anything else on
    the first line is data (the declared sample has no header line).
    """
    if record is MALFORMED:
        return False
    if len(record) != len(COLUMNS):
        return False
    return tuple(field.strip().lower() for field in record) == COLUMNS


def parse_amount(text):
    """Return the exact numeric value of an amount cell, or None when unusable.

    Only a plain decimal is accepted (AMB-004). The value is returned as an
    exact ``Fraction`` so that summing never accumulates binary error.
    """
    if not AMOUNT.match(text):
        return None
    try:
        return Fraction(Decimal(text))
    except (InvalidOperation, ValueError):  # defensive: regex already guarantees shape
        return None


def parse_region(text):
    """Return the region key of a cell, or None when the cell is unusable.

    AMB-005 (exact): the region is used verbatim as the group key, so case and
    internal spacing are significant. A region that is empty or whitespace-only
    is unusable under AMB-001 / REQ-004.
    """
    if text.strip() == "":
        return None
    return text


def parse_row(record):
    """Return ``(region, amount)`` for a usable row, or None when it is unusable.

    A row is unusable when it does not have exactly two fields, when the region
    is empty or whitespace-only, or when the amount is not a plain decimal
    (REQ-004, AMB-004).
    """
    if record is MALFORMED:
        return None
    if len(record) != len(COLUMNS):
        return None
    region = parse_region(record[0])
    if region is None:
        return None
    amount = parse_amount(record[1])
    if amount is None:
        return None
    return region, amount


def read_records(handle):
    """Yield every CSV record, turning a parser-level error into MALFORMED.

    One pathological record must not abort the run: it becomes an unusable row,
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


def format_cents(cents):
    """Render an integer number of cents with exactly two decimal places.

    The caller has already rounded half away from zero at the second decimal
    place (AMB-003). A zero value never carries a minus sign.
    """
    sign = "-" if cents < 0 else ""
    magnitude = abs(cents)
    return "%s%d.%02d" % (sign, magnitude // 100, magnitude % 100)


def rounded_cents(value):
    """Round an exact value half away from zero at the second decimal place.

    AMB-003 (half-up): an exact half rounds away from zero. The comparison is
    on the exact remainder, so a repeating decimal is never truncated to a
    nearby binary approximation first.
    """
    sign = -1 if value < 0 else 1
    numerator = abs(value.numerator) * 100
    denominator = value.denominator
    whole, remainder = divmod(numerator, denominator)
    # AMB-003 (half-up): `>=` sends an exact half away from zero; `>` would be
    # the truncate behaviour this decision rejects.
    if remainder * 2 >= denominator:
        whole += 1
    return sign * whole


def format_value(value):
    """Render an exact value with two decimals, half away from zero (AMB-003)."""
    return format_cents(rounded_cents(value))


def summarise(records):
    """Build the report lines from an iterable of CSV records.

    Returns the region lines in ascending UTF-8 byte order of the region string,
    then exactly one TOTAL line, then the SKIPPED line when any row was skipped.
    """
    iterator = iter(records)
    try:
        first = next(iterator)
    except StopIteration:
        # No records at all: there is no data row and nothing to aggregate.
        return ["TOTAL 0 0.00"]

    if looks_like_header(first):
        # REQ-001: the header row is never a data row, so it is not counted and
        # not skipped either.
        data = iterator
    else:
        # The declared sample has no header: its first line is a data row.
        data = _prepend(first, iterator)

    groups = {}  # region -> [count, exact raw sum]
    skipped = 0

    for record in data:
        parsed = parse_row(record)
        if parsed is None:
            # AMB-001 (skip-count): an unusable row is skipped and excluded from
            # every aggregate, and the run reports it on the SKIPPED line instead
            # of aborting. One counter increment per unusable row.
            skipped += 1
            continue
        region, amount = parsed
        group = groups.get(region)
        if group is None:
            # AMB-002 (merge): a repeated region is not an error or a conflict;
            # its rows accumulate into the one aggregate printed for it.
            groups[region] = [1, amount]
        else:
            group[0] += 1
            # AMB-002 (merge): every occurrence counts as its own order, so the
            # count and the raw sum grow with each row of this region.
            group[1] += amount

    lines = []
    total_count = 0
    total_cents = 0
    # REQ-005: region lines are emitted in ascending byte order of the region
    # string, so the report is deterministic and independent of row order.
    for region in sorted(groups, key=lambda name: name.encode("utf-8")):
        count, raw_sum = groups[region]
        # REQ-006: the printed sum is the rounded total of the raw amounts; the
        # printed mean divides the UNROUNDED region sum by the count and rounds
        # only for printing.
        sum_cents = rounded_cents(raw_sum)
        mean = Fraction(raw_sum, count)
        lines.append(
            "%s %d %s %s"
            % (region, count, format_cents(sum_cents), format_value(mean))
        )
        total_count += count
        # REL-003 (additivity): the totals line is the sum of the very printed
        # region sums, so the per-region sums add up to the TOTAL sum exactly.
        total_cents += sum_cents

    # REQ-003: exactly one totals line, after the region lines. With no data
    # rows it is the only line: "TOTAL 0 0.00".
    lines.append("TOTAL %d %s" % (total_count, format_cents(total_cents)))
    # AMB-001 (skip-count): report how many rows were skipped. A clean file
    # prints no SKIPPED line, so a header-only file is exactly one line
    # (REQ-003) and the line stays the final line of the report.
    if skipped:
        lines.append("SKIPPED %d" % skipped)
    return lines


def _prepend(head, iterator):
    """Yield ``head`` then everything from ``iterator``."""
    yield head
    for item in iterator:
        yield item


def main(argv):
    """Entry point used by ``summary.sh``; returns the process exit status."""
    if len(argv) != 2:
        sys.stderr.write(USAGE)
        return 2

    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            lines = summarise(read_records(handle))
    except OSError as exc:
        sys.stderr.write("summary.sh: cannot read %s: %s\n" % (path, exc.strerror or exc))
        return 1
    except UnicodeDecodeError:
        sys.stderr.write("summary.sh: %s is not valid UTF-8 text\n" % path)
        return 1

    # REQ-001: stdout carries report lines only; diagnostics go to stderr.
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
