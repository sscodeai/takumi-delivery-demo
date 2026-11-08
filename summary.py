#!/usr/bin/env python3
"""Per-region revenue and average order value from a ``region,amount`` CSV.

Usage: bash summary.sh <csv>

The report is::

    <region> <count> <sum> <mean>     one line per region, sorted by name
    TOTAL <count> <sum>               exactly once, after the region lines
    SKIPPED <skipped-count>           always last, even when the count is 0

Columns are located by header name when the first non-blank record is a
header (it names ``region`` and/or ``amount``).  The requirement's declared
sample ships *without* a header, so a first record that names neither column
is treated as the first data row with the columns in ``region,amount`` order.
Any extra columns, and any column order, are irrelevant once the header is
recognised.

Only the Python 3 standard library is used: no install step, no network
access, and the input file is opened read-only.  Every sum and mean is
printed with exactly two decimal places, with no thousands separator.

The ambiguities settled for this delivery are marked with greppable
``AMB-nnn`` comments below and recorded in ``docs/decisions.md``.
"""

from __future__ import annotations

import csv
import itertools
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

REQUIRED_COLUMNS = ("region", "amount")
DEFAULT_COLUMNS = ("region", "amount")
CENT = Decimal("0.01")
# Wide enough that adding and dividing ordinary monetary amounts is exact
# before the final two-decimal rounding.
WORKING_PRECISION = 60


class InputError(Exception):
    """The input cannot be read as a ``region,amount`` sales CSV."""


def _header_name(cell: str) -> str:
    """Normalise a header cell: drop a BOM, surrounding blanks and case."""
    return cell.strip().lstrip("\ufeff").lower()


def looks_like_header(record: Sequence[str]) -> bool:
    """True when the record names at least one of the required columns.

    A data row has a region and a numeric amount, so it cannot name a
    ``region``/``amount`` column.  Recognising *one* name is enough to call
    the record a header: a header that names only ``region`` is still a
    malformed header and must stop the run rather than be counted as data.
    """
    return any(_header_name(cell) in REQUIRED_COLUMNS for cell in record)


def resolve_columns(header: Sequence[str]) -> Tuple[int, int]:
    """Return the (region, amount) indices named by a header record."""
    positions: Dict[str, int] = {}
    for index, cell in enumerate(header):
        positions.setdefault(_header_name(cell), index)
    missing = [name for name in REQUIRED_COLUMNS if name not in positions]
    # REQ-002: columns are found by header name, never by position.  A header
    # that does not name both columns is unusable, so the run stops with a
    # diagnostic and prints no partial report.
    if missing:
        raise InputError(
            "header is missing required column(s): " + ", ".join(missing)
        )
    return positions["region"], positions["amount"]


def is_blank_record(record: Sequence[str]) -> bool:
    """True for a physically blank line (no cell carries any text)."""
    # REQ-002: a blank line is neither a record nor a skipped row.
    return not record or all(cell.strip() == "" for cell in record)


def parse_amount(value: str) -> Optional[Decimal]:
    """Return the row's amount as a Decimal, or None when it is unusable."""
    text = value.strip()
    if text == "":
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    # ``NaN``/``Infinity`` are accepted by Decimal but are not sales amounts.
    if not amount.is_finite():
        return None
    # AMB-004 (include): a well-formed negative amount is a refund and is
    # returned like any other amount, so it reduces the region's revenue.
    return amount


def summarise_records(
    header: Sequence[str], records: Iterable[Sequence[str]]
) -> Tuple[Dict[str, int], Dict[str, Decimal], int]:
    """Aggregate accepted records per region and count malformed rows."""
    region_index, amount_index = resolve_columns(header)
    needed = max(region_index, amount_index)
    counts: Dict[str, int] = {}
    totals: Dict[str, Decimal] = {}
    skipped = 0
    for record in records:
        if is_blank_record(record):
            continue
        # AMB-001 (skip-count): a row too short to carry the named columns is
        # skipped, excluded from every aggregate and counted on SKIPPED.
        if len(record) <= needed:
            skipped += 1
            continue
        region = record[region_index].strip()
        amount = parse_amount(record[amount_index])
        # AMB-001 (skip-count): an empty region or a non-numeric amount makes
        # the row unusable; it is skipped and counted, never aggregated.
        if region == "" or amount is None:
            skipped += 1
            continue
        # AMB-002 (merge): every row is its own order.  There is deliberately
        # no de-duplication, so a repeated region+amount counts twice and its
        # amount is added twice.
        counts[region] = counts.get(region, 0) + 1
        totals[region] = totals.get(region, Decimal(0)) + amount
    return counts, totals, skipped


def _mean(total: Decimal, count: int) -> Decimal:
    """Divide at a wide precision; the caller rounds the printed value."""
    with localcontext() as context:
        context.prec = WORKING_PRECISION
        return total / count


def format_amount(value: Decimal) -> str:
    """Render an amount with exactly two decimal places."""
    # AMB-003 (half-up): round half away from zero to exactly two decimals.
    with localcontext() as context:
        context.prec = WORKING_PRECISION
        rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)
    # Avoid printing "-0.00" when refunds cancel out a region's revenue.
    if rounded == 0:
        rounded = abs(rounded)
    return format(rounded, "f")


def format_report(
    counts: Dict[str, int], totals: Dict[str, Decimal], skipped: int
) -> List[str]:
    """Render the region lines, then TOTAL, then SKIPPED."""
    lines: List[str] = []
    # REQ-003 / REQ-008: sort by the UTF-8 bytes of the region name, so the
    # order is lexicographic, locale-independent and independent of row order.
    for region in sorted(counts, key=lambda name: name.encode("utf-8")):
        count = counts[region]
        total = totals[region]
        lines.append(
            f"{region} {count} {format_amount(total)} "
            f"{format_amount(_mean(total, count))}"
        )
    total_count = sum(counts.values())
    total_sum = sum(totals.values(), Decimal(0))
    # REQ-004: exactly one TOTAL line carrying only the two numbers.
    lines.append(f"TOTAL {total_count} {format_amount(total_sum)}")
    # REQ-005: the SKIPPED line is always printed, exactly once, last.
    lines.append(f"SKIPPED {skipped}")
    return lines


def _non_blank_records(reader: Iterable[Sequence[str]]) -> Iterator[Sequence[str]]:
    for record in reader:
        if is_blank_record(record):
            continue
        yield record


def summarise_file(path: str) -> Tuple[Dict[str, int], Dict[str, Decimal], int]:
    """Read ``path`` as a sales CSV and return its aggregates and skip count."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            stream = _non_blank_records(reader)
            try:
                first = next(stream)
            except StopIteration:
                # REQ-001 / REQ-009: a readable file with no records at all is
                # a valid empty report, not an error.
                return {}, {}, 0
            if looks_like_header(first):
                header = first
                records: Iterable[Sequence[str]] = stream
            else:
                # The declared sample has no header row: use the declared
                # column order and keep the first record as data (REQ-002).
                header = DEFAULT_COLUMNS
                records = itertools.chain([first], stream)
            return summarise_records(header, records)
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"cannot decode {path} as UTF-8: {exc}") from exc
    except csv.Error as exc:
        raise InputError(f"cannot parse {path} as CSV: {exc}") from exc


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: bash summary.sh <csv>\n")
        return 2
    try:
        counts, totals, skipped = summarise_file(argv[1])
    except InputError as exc:
        # REQ-001: a diagnostic on stderr, nothing on stdout, nonzero exit.
        sys.stderr.write(f"summary: {exc}\n")
        return 1
    report = "".join(line + "\n" for line in format_report(counts, totals, skipped))
    try:
        # Write UTF-8 bytes directly so the output does not depend on locale.
        sys.stdout.buffer.write(report.encode("utf-8"))
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
