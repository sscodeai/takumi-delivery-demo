#!/usr/bin/env bash
# summary.sh -- per-station temperature summary for a daily readings CSV.
#
# Usage: bash summary.sh <input.csv>
#
# Contract (docs/requirements/intake.yaml):
#   run:          bash summary.sh {csv}
#   station line: <station> <count> <min> <max> <mean>
#   skipped line: SKIPPED <count>
#   total line:   TOTAL <count>
#
# Confirmed decisions:
#   AMB-001 skip-count  malformed rows are skipped, excluded from every aggregate,
#                       and counted on the SKIPPED line
#   AMB-002 merge       every occurrence of a repeated (date, station) key counts
#                       as its own reading and contributes to the aggregate
#   AMB-003 half-up     min/max/mean round half away from zero to one decimal place
#   AMB-004 ascending   station lines are sorted by ascending byte-wise station id
#   AMB-005 valid-only  TOTAL counts valid readings only (the sum of the station counts)
#
# The aggregation runs in Python 3 using only the standard library. Temperatures
# are kept as exact rationals (fractions.Fraction) and rendered with integer
# arithmetic, so the half-up rule is exact and row order cannot perturb a value.
# The tool reads exactly one local file and performs no network I/O, so it works
# on a laptop with the network disabled.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  printf 'usage: bash summary.sh <input.csv>\n' >&2
  exit 2
fi

exec python3 - "$1" <<'PY'
import csv
import re
import sys
from datetime import date
from fractions import Fraction

# A well-formed date is a zero-padded ISO-8601 calendar date, optionally followed
# by a time suffix. The calendar part must name a real day.
DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ].*)?$")

# A well-formed temperature is a plain decimal number with an optional sign.
# Thousand separators, blanks, hex, NaN, Infinity and exponent notation are not
# numeric temperatures in a CSV export.
TEMP_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")

# The declared header, consumed and never treated as a reading. A first line that
# is not this header (for example the document's header-less sample) is treated
# as a reading in the declared positional order instead.
HEADER_NAMES = ("date", "station", "temperature_c")

# A single pathological record must never abort the run (REQ-005), so keep overly
# long fields from raising a csv error that would escape the per-row handling.
try:
    csv.field_size_limit(2 ** 31 - 1)
except (OverflowError, ValueError):  # pragma: no cover - defensive
    pass

# Python 3.11 caps int-to-str conversion by default. A record with thousands of
# digits is still a number the tool must be able to render, so raise the cap well
# above anything a temperature export can hold.
if hasattr(sys, "set_int_max_str_digits"):
    try:
        sys.set_int_max_str_digits(1000000)
    except (ValueError, OverflowError):  # pragma: no cover - defensive
        pass


def is_date(text):
    """True when the field is a calendar-valid ISO-8601 date."""
    match = DATE_RE.match(text)
    if match is None:
        return False
    year, month, day = (int(part) for part in match.groups())
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def is_temperature(text):
    """True when the field is a plain decimal temperature."""
    return TEMP_RE.match(text) is not None


def render_one_decimal(value):
    """Render a value already scaled by ten as one decimal, half away from zero.

    Callers multiply the reading (or the mean) by ten and pass the exact
    Fraction here; rounding happens in integer arithmetic, so no binary floating
    point value is ever involved in the rendered digit.
    """
    numerator, denominator = value.numerator, value.denominator
    negative = numerator < 0
    if negative:
        numerator = -numerator
    quotient, remainder = divmod(numerator, denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    if quotient == 0:
        return "0.0"  # normalise negative zero
    return "%s%d.%d" % ("-" if negative else "", quotient // 10, quotient % 10)


def render_reading(value):
    """Render a reading as one decimal place, half away from zero (AMB-003)."""
    return render_one_decimal(value * 10)


def render_mean(total, count):
    """Render the arithmetic mean as one decimal, half away from zero (AMB-003)."""
    return render_one_decimal((total / count) * 10)


def read_rows(handle):
    """Yield the fields of every CSV record, tolerating parser-level errors.

    A record the csv module itself rejects is reported as a ``None`` row so the
    caller can count it as malformed without the run aborting (REQ-005).
    """
    reader = csv.reader(handle)
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error:
            yield None


def aggregate(path):
    """Aggregate the CSV at ``path``; return (station rows, skipped, total).

    ``station rows`` is a list of ``(station, count, min, max, mean)`` tuples in
    ascending byte-wise station order. A row is valid when it has three fields, a
    non-empty station id, a calendar-valid ISO date and a plain decimal
    temperature. Every other row is counted as skipped and never changes an
    aggregate (AMB-001). Every occurrence of a repeated (date, station) key is
    its own reading (AMB-002). ``total`` counts valid readings only (AMB-005).
    """
    stations = {}  # station id -> [count, min, max, sum]
    skipped = 0
    total = 0
    header_seen = False
    date_i, station_i, temperature_i = 0, 1, 2

    # Decode with replacement so an undecodable byte can never abort the run
    # (REQ-005): it turns the affected field into a malformed value instead.
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in read_rows(handle):
            if row is None:  # a record the parser rejected is malformed
                skipped += 1
                continue

            if not header_seen:
                header_seen = True
                names = [column.strip().lower() for column in row]
                if all(name in names for name in HEADER_NAMES):
                    date_i = names.index("date")
                    station_i = names.index("station")
                    temperature_i = names.index("temperature_c")
                    # The declared header is consumed and is never a reading.
                    continue

            if len(row) != 3:
                skipped += 1
                continue

            station = row[station_i]
            if station == "":
                skipped += 1
                continue
            if not is_date(row[date_i]):
                skipped += 1
                continue
            if not is_temperature(row[temperature_i]):
                skipped += 1
                continue

            # AMB-002 merge: the aggregate is keyed by station only, so a
            # repeated (date, station) row is folded in as its own reading.
            value = Fraction(row[temperature_i])
            entry = stations.get(station)
            if entry is None:
                stations[station] = [1, value, value, value]
            else:
                entry[0] += 1
                if value < entry[1]:
                    entry[1] = value
                if value > entry[2]:
                    entry[2] = value
                entry[3] += value
            total += 1

    rows = []
    # AMB-004: ascending byte-wise station id order.
    for station in sorted(stations, key=lambda name: name.encode("utf-8")):
        count, minimum, maximum, accumulated = stations[station]
        rows.append(
            (
                station,
                count,
                render_reading(minimum),
                render_reading(maximum),
                render_mean(accumulated, count),
            )
        )
    return rows, skipped, total


def main(path):
    try:
        rows, skipped, total = aggregate(path)
    except OSError as exc:
        sys.stderr.write("summary.sh: cannot read %s: %s\n" % (path, exc))
        return 1

    out = ["%s %d %s %s %s" % row for row in rows]
    out.append("SKIPPED %d" % skipped)
    out.append("TOTAL %d" % total)
    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
PY
