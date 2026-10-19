"""An independent reference implementation for the intake document.

This module deliberately shares no code with summary.sh. It reads a CSV document
by splitting on commas (the declared input world has no quoting), keeps
temperatures as exact rationals (fractions.Fraction) and renders one decimal
place with integer arithmetic, half away from zero. It exists so the test suite
can compare the delivered tool against a second implementation of the same
contract: an error in one is unlikely to be repeated by the other.
"""

import re
from datetime import date, datetime
from fractions import Fraction

HEADER = "date,station,temperature_c"

# The document declares the date column as a date and the measure column as a
# number. The tool accepts a zero-padded ISO-8601 date with an optional time
# suffix and a plain (non-exponent) decimal temperature.
DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(.*)$")
TEMP_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")
HEADER_NAMES = ("date", "station", "temperature_c")


def is_date(text):
    match = DATE_RE.match(text)
    if match is None:
        return False
    year, month, day = (int(part) for part in match.groups()[:3])
    try:
        date(year, month, day)
    except ValueError:
        return False
    suffix = match.group(4)
    if suffix == "":
        return True
    if suffix[0] not in "T ":
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_temperature(text):
    return TEMP_RE.match(text) is not None


def round_half_up_one(value):
    """Render a Fraction with exactly one decimal, half away from zero."""
    scaled = value * 10
    numerator, denominator = scaled.numerator, scaled.denominator
    negative = numerator < 0
    if negative:
        numerator = -numerator
    quotient, remainder = divmod(numerator, denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    if quotient == 0:
        return "0.0"
    return "%s%d.%d" % ("-" if negative else "", quotient // 10, quotient % 10)


def reference_lines(text):
    """Return the exact expected output lines for a CSV document."""
    rows = text.split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    stations = {}
    skipped = 0
    total = 0
    header_seen = False
    date_i, station_i, temperature_i = 0, 1, 2

    for row in rows:
        # An empty physical line is a record with no fields in the declared
        # world, so it is malformed once the header has been consumed.
        fields = row.split(",")
        if not header_seen:
            header_seen = True
            names = [field.strip().lower() for field in fields]
            if all(name in names for name in HEADER_NAMES):
                date_i = names.index("date")
                station_i = names.index("station")
                temperature_i = names.index("temperature_c")
                # The declared header is consumed, never a reading. A first line
                # that is not the declared header is a reading instead.
                continue
        if len(fields) != 3:
            skipped += 1
            continue
        station = fields[station_i]
        if station == "":
            skipped += 1
            continue
        if not is_date(fields[date_i]):
            skipped += 1
            continue
        if not is_temperature(fields[temperature_i]):
            skipped += 1
            continue

        value = Fraction(fields[temperature_i])
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

    out = []
    for station in sorted(stations, key=lambda name: name.encode("utf-8")):
        count, minimum, maximum, accumulated = stations[station]
        mean = accumulated / count
        out.append(
            "%s %d %s %s %s"
            % (
                station,
                count,
                round_half_up_one(minimum),
                round_half_up_one(maximum),
                round_half_up_one(mean),
            )
        )
    out.append("SKIPPED %d" % skipped)
    out.append("TOTAL %d" % total)
    return out


def reference_output(text):
    return "\n".join(reference_lines(text)) + "\n"
