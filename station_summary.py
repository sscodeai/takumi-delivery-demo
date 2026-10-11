#!/usr/bin/env python3
"""Station temperature summary HTTP service.

Usage: python3 station_summary.py <input.csv> <port>

The service reads a daily temperature CSV export (``date,station,temperature_c``)
once at start-up, aggregates it per station and answers ``GET /summary`` with the
per-station summary the requirement document declares.

The response is a single JSON array: one compact JSON object per line, which is
exactly the line shapes the document declares (``station_object``,
``skipped_object``, ``total_object``) and at the same time one valid JSON
document.  Nothing about the wire format depends on YAML quoting:

    [
    {"station":"ALPHA","count":3,"min":9.5,"max":11.6,"mean":10.5},
    {"station":"BRAVO","count":2,"min":-2.5,"max":-1.5,"mean":-2.0},
    {"skipped":0},
    {"total":5}
    ]

The service binds ``127.0.0.1`` only, makes no outbound network call and runs on
the Python 3 standard library alone.  The summary is computed from the file once
and served from memory, so a year of readings is answered without re-reading it.
"""

import csv
import json
import re
import sys
from datetime import date
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# A well-formed date is a zero-padded ISO-8601 calendar date, optionally followed
# by a time suffix.  The calendar part must name a real day.
DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ].*)?$")

# A well-formed temperature is a plain decimal number with an optional sign.
# Thousand separators, blanks, hex, NaN, Infinity and exponent notation are not
# numeric temperatures in a CSV export; the requirement document's world uses
# plain decimals.
TEMP_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")

# The declared header, consumed and never treated as a reading.  A first line
# that is not this header is treated as a reading in positional order instead.
HEADER_NAMES = ("date", "station", "temperature_c")

# A pathological record must never abort the service (REQ-005), so keep overly
# long fields from raising a csv error that would escape the per-row handling.
try:
    csv.field_size_limit(2 ** 31 - 1)
except (OverflowError, ValueError):  # pragma: no cover - defensive
    pass

# Python 3.11 caps int-to-str conversion by default; a reading with thousands of
# digits is still one the service must be able to render.
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
    """Render a Fraction reading with one decimal place, half away from zero."""
    return render_ratio(value.numerator * 10, value.denominator)


def render_mean(accumulated, count):
    """Render the arithmetic mean of Fraction readings with one decimal place."""
    return render_ratio(accumulated.numerator * 10, accumulated.denominator * count)


def compact_object(pairs):
    """Render an ordered sequence of key/value pairs as compact JSON.

    Values are used verbatim, so the numbers keep exactly the decimal text
    ``render_reading``/``render_mean`` produced rather than a float rendering.
    """
    return "{%s}" % ",".join('"%s":%s' % (key, value) for key, value in pairs)


def aggregate(path):
    """Aggregate the CSV at ``path`` and return (station_rows, skipped, total).

    ``station_rows`` is a list of ``(station, count, min, max, mean)`` tuples in
    ascending byte-wise station order.  A row is valid when it has three fields,
    a non-empty station id, a calendar-valid ISO date and a plain decimal
    temperature.  Every other row is counted as skipped and never changes an
    aggregate (AMB-001).  Every occurrence of a repeated (date, station) key is
    its own reading (AMB-002).  ``total`` counts valid readings only (AMB-005).
    """
    stations = {}
    skipped = 0
    total = 0
    header_seen = False
    date_i, station_i, temperature_i = 0, 1, 2

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
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
                    # The declared header is consumed, never a reading.  A first
                    # line that is not the declared header is a reading in the
                    # declared positional order instead.
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

            value = Fraction(row[temperature_i])
            # AMB-002 merge: the aggregate is keyed by station only, so a
            # repeated (date, station) row is folded in as its own reading.
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


def summarise(path):
    """Aggregate the CSV at ``path`` and return the declared report as bytes."""
    rows, skipped, total = aggregate(path)
    lines = ["["]
    objects = []
    for station, count, minimum, maximum, mean in rows:
        objects.append(
            compact_object(
                (
                    ("station", json.dumps(station, ensure_ascii=False)),
                    ("count", "%d" % count),
                    ("min", minimum),
                    ("max", maximum),
                    ("mean", mean),
                )
            )
        )
    objects.append(compact_object((("skipped", "%d" % skipped),)))
    objects.append(compact_object((("total", "%d" % total),)))
    # One object per line and the array separators on their own lines: the body
    # stays one valid JSON document while every object line matches its declared
    # shape exactly, with no trailing comma to trip a shape anchored at the end.
    for index, payload in enumerate(objects):
        if index:
            lines.append(",")
        lines.append(payload)
    lines.append("]")
    return ("\n".join(lines) + "\n").encode("utf-8")


class SummaryHandler(BaseHTTPRequestHandler):
    """Serve the pre-computed summary report on ``GET /summary``."""

    server_version = "station-summary/1.0"
    protocol_version = "HTTP/1.1"

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _summary(self):
        path = urlsplit(self.path).path
        return path == "/summary" or path == "/summary/"

    def do_GET(self):
        if self._summary():
            self._send(200, self.server.summary_body, "application/json")
        else:
            self._send(404, b'{"error":"not found"}\n', "application/json")

    def do_HEAD(self):
        if self._summary():
            body = self.server.summary_body
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *args):  # noqa: D102 - keep the service quiet
        pass


def serve(path, port):
    """Aggregate ``path`` and serve it on the given localhost port until killed."""
    body = summarise(path)
    server = ThreadingHTTPServer(("127.0.0.1", port), SummaryHandler)
    server.daemon_threads = True
    server.summary_body = body
    server.serve_forever(poll_interval=0.2)


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: station_summary.py <input.csv> <port>\n")
        return 2
    path, port_text = argv[1], argv[2]
    if not port_text.isdigit():
        sys.stderr.write("station_summary.py: port %r is not a whole number\n" % port_text)
        return 2
    port = int(port_text)
    if not 1 <= port <= 65535:
        sys.stderr.write("station_summary.py: port %d is out of range\n" % port)
        return 2
    try:
        serve(path, port)
    except OSError as exc:
        sys.stderr.write("station_summary.py: cannot read %s: %s\n" % (path, exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
