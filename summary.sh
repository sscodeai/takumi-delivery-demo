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
# The aggregation runs in Python 3 using only the standard library. Decimal values
# and integer-ratio rendering make the half-up rule exact instead of subject to
# binary floating point. The tool reads exactly one local file and performs no
# network I/O.
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
from decimal import Decimal, DecimalException, localcontext

# Fold rows with far more precision than a real temperature sum needs so that the
# order in which rows are read cannot change the accumulated value.
CONTEXT_PRECISION = 100000

# A well-formed date is a zero-padded ISO-8601 calendar date, optionally followed
# by a time suffix. The calendar part must name a real day.
DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ].*)?$")

# A well-formed temperature is a plain decimal number with an optional sign.
# Thousand separators, blanks, hex, NaN, Infinity and exponent notation are not
# numeric temperatures in a CSV export.
TEMP_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")

# The declared header, consumed and never treated as a reading. A first line that
# is not this header (for example the pipeline's header-less sample) is treated as
# a reading in the declared positional order instead.
HEADER_NAMES = ("date", "station", "temperature_c")

# A single pathological record must never abort the run (REQ-005), so keep overly
# long fields from raising a csv error that would escape the per-row handling.
try:
    csv.field_size_limit(2 ** 31 - 1)
except (OverflowError, ValueError):
    pass

# Python 3.11 caps int-to-str conversion by default. A record with thousands of
# digits is still a number the tool must be able to render, so raise the cap
# well above the precision this tool computes with.
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


def render_ratio(numerator, denominator):
    """Render numerator/denominator with one decimal, half away from zero.

    Exact integer arithmetic: the scaled quotient is rounded up whenever the
    remainder is at least half the divisor, which is what AMB-003 chose.
    """
    negative = (numerator < 0) != (denominator < 0)
    numerator = -numerator if numerator < 0 else numerator
    denominator = -denominator if denominator < 0 else denominator
    quotient, remainder = divmod(numerator, denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    if quotient == 0:
        return "0.0"  # normalise negative zero
    sign = "-" if negative else ""
    return "%s%d.%d" % (sign, quotient // 10, quotient % 10)


def render_reading(value):
    """Render a Decimal reading with one decimal place, half away from zero."""
    numerator, denominator = value.as_integer_ratio()
    return render_ratio(numerator * 10, denominator)


def render_mean(accumulated, count):
    """Render the arithmetic mean of Decimal values with one decimal place."""
    numerator, denominator = accumulated.as_integer_ratio()
    return render_ratio(numerator * 10, denominator * count)


def main(path):
    with localcontext() as ctx:
        ctx.prec = CONTEXT_PRECISION

        try:
            handle = open(path, "r", encoding="utf-8-sig", newline="")
        except OSError as exc:
            sys.stderr.write("summary.sh: cannot read %s: %s\n" % (path, exc))
            return 1

        # station id -> [count, min, max, sum]
        stations = {}
        skipped = 0
        total = 0
        header_seen = False
        date_i, station_i, temperature_i = 0, 1, 2

        with handle:
            reader = csv.reader(handle)
            while True:
                try:
                    row = next(reader)
                except StopIteration:
                    break
                except csv.Error:
                    # A record the parser itself rejects is malformed.
                    skipped += 1
                    continue

                if not header_seen:
                    header_seen = True
                    names = [column.strip().lower() for column in row]
                    if all(name in names for name in HEADER_NAMES):
                        date_i = names.index("date")
                        station_i = names.index("station")
                        temperature_i = names.index("temperature_c")
                        # The declared header is consumed and never treated as a
                        # reading. A first line that is not the declared header is
                        # a reading in the positional column order.
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

                try:
                    temperature = Decimal(row[temperature_i])
                except DecimalException:
                    skipped += 1
                    continue
                if not temperature.is_finite():
                    skipped += 1
                    continue

                # AMB-002 merge: the aggregate is keyed by station only, so a
                # repeated (date, station) row is folded in as its own reading.
                entry = stations.get(station)
                if entry is None:
                    stations[station] = [1, temperature, temperature, temperature]
                else:
                    entry[0] += 1
                    if temperature < entry[1]:
                        entry[1] = temperature
                    if temperature > entry[2]:
                        entry[2] = temperature
                    entry[3] += temperature
                total += 1

        # AMB-004: ascending byte-wise station id order.
        out = []
        for station in sorted(stations, key=lambda name: name.encode("utf-8")):
            count, minimum, maximum, accumulated = stations[station]
            out.append(
                "%s %d %s %s %s"
                % (
                    station,
                    count,
                    render_reading(minimum),
                    render_reading(maximum),
                    render_mean(accumulated, count),
                )
            )
        out.append("SKIPPED %d" % skipped)
        out.append("TOTAL %d" % total)
        sys.stdout.write("\n".join(out) + "\n")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
PY
