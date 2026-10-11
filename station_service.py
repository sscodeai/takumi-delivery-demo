#!/usr/bin/env python3
"""Station temperature summary HTTP service.

Usage: python3 station_service.py <input.csv> <port>

The service reads a daily temperature CSV export (``date,station,temperature_c``)
once at start-up, aggregates it per station and answers ``GET /summary`` with one
declared output line per JSON object:

    {"station":"<station>","count":<count>,"min":<min>,"max":<max>,"mean":<mean>}
    {"skipped":<skipped-count>}
    {"total":<count>}

The single quotes the requirement document writes around each declared
``output_format`` shape are YAML scalar quoting, not wire bytes: the endpoint
answers each line with the compact JSON object the shape describes, so every
line in the response body parses as JSON.

It binds ``127.0.0.1`` only, makes no outbound network call and runs on the
standard library alone.  The summary is served from memory, so it stays fast on
a year of readings.
"""

import csv
import json
import re
import sys
from datetime import date
from decimal import Decimal, DecimalException, localcontext
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# Fold rows with far more precision than a real temperature sum needs so that the
# order in which rows are read cannot change the accumulated value.
CONTEXT_PRECISION = 100000

# A well-formed date is a zero-padded ISO-8601 calendar date, optionally followed
# by a time suffix.  The calendar part must name a real day.
DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ].*)?$")

# A well-formed temperature is a plain decimal number with an optional sign.
TEMP_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")

# The declared header, consumed and never treated as a reading.  A first line
# that is not this header is treated as a reading in positional order instead.
HEADER_NAMES = ("date", "station", "temperature_c")

# A pathological record must never abort the service, so keep overly long fields
# from raising a csv error that would escape the per-row handling.
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
    remainder is at least half the divisor (AMB-003).
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
    """Render the arithmetic mean of Fraction values, half away from zero."""
    return render_ratio(accumulated.numerator * 10, accumulated.denominator * count)


def summarise(path):
    """Aggregate the CSV at ``path`` and return the JSON body as bytes.

    A row is valid when it has three fields, a non-empty station id, a
    calendar-valid ISO date and a plain decimal temperature.  Every other row is
    counted as skipped and never changes an aggregate (AMB-001).  Every
    occurrence of a repeated (date, station) key is its own reading (AMB-002).
    """
    with localcontext() as ctx:
        ctx.prec = CONTEXT_PRECISION

        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            stations = {}
            skipped = 0
            total = 0
            header_seen = False
            date_i, station_i, temperature_i = 0, 1, 2

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
                    temperature = Fraction(Decimal(row[temperature_i]))
                except (DecimalException, ValueError, ZeroDivisionError):
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

        lines = []
        # AMB-004: ascending byte-wise station id order.
        for station in sorted(stations, key=lambda name: name.encode("utf-8")):
            count, minimum, maximum, accumulated = stations[station]
            lines.append(
                '{"station":%s,"count":%d,"min":%s,"max":%s,"mean":%s}'
                % (
                    json.dumps(station, ensure_ascii=False),
                    count,
                    render_reading(minimum),
                    render_reading(maximum),
                    render_mean(accumulated, count),
                )
            )
        lines.append('{"skipped":%d}' % skipped)
        # AMB-005 valid-only: the total is the sum of the per-station counts.
        lines.append('{"total":%d}' % total)
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

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/summary":
            self._send(200, self.server.summary_body, "application/json")
        else:
            self._send(404, b'{"error":"not found"}\n', "application/json")

    def do_HEAD(self):
        path = urlsplit(self.path).path
        if path == "/summary":
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
    """Aggregate ``path`` and serve it on the given port until killed."""
    body = summarise(path)
    server = ThreadingHTTPServer(("127.0.0.1", port), SummaryHandler)
    server.daemon_threads = True
    server.summary_body = body
    server.serve_forever()


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: station_service.py <input.csv> <port>\n")
        return 2
    path, port_text = argv[1], argv[2]
    if not port_text.isdigit():
        sys.stderr.write("station_service.py: port %r is not a whole number\n" % port_text)
        return 2
    port = int(port_text)
    if not 1 <= port <= 65535:
        sys.stderr.write("station_service.py: port %d is out of range\n" % port)
        return 2
    try:
        serve(path, port)
    except OSError as exc:
        sys.stderr.write("station_service.py: cannot read %s: %s\n" % (path, exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
