"""Unit tests for the service's aggregation primitives and report assembly.

These tests import ``station_summary`` directly and exercise the pure helpers
(``render_ratio``, ``render_reading``, ``render_mean``, ``is_date``,
``is_temperature``) plus ``summarise`` and ``main`` at the function boundary.
The process-boundary HTTP tests live in ``test_service.py``; together they cover
the unit and integration halves of the requirement document.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import station_summary as service  # noqa: E402 - path set above


def write_csv(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    handle.write(text)
    handle.close()
    return handle.name


def write_csv_bytes(payload):
    """Write raw bytes, for a file that is readable but not valid UTF-8."""
    handle = tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False)
    handle.write(payload)
    handle.close()
    return handle.name


def report_lines(text):
    """Summarise ``text`` and return the JSON objects it reports."""
    path = write_csv(text)
    try:
        body = service.summarise(path).decode("utf-8")
    finally:
        os.unlink(path)
    payloads = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped in ("[", "]", ","):
            continue
        payloads.append(json.loads(stripped.rstrip(",")))
    return payloads


class RenderRatioTests(unittest.TestCase):
    """AMB-003 at its narrowest: the renderer takes tenths and rounds half up."""

    def test_exact_values_carry_one_decimal(self):
        self.assertEqual(service.render_ratio(100, 1), "10.0")
        self.assertEqual(service.render_ratio(10, 1), "1.0")
        self.assertEqual(service.render_ratio(0, 1), "0.0")
        self.assertEqual(service.render_ratio(5, 1), "0.5")

    def test_half_rounds_away_from_zero(self):
        self.assertEqual(service.render_ratio(5, 2), "0.3")
        self.assertEqual(service.render_ratio(-5, 2), "-0.3")
        self.assertEqual(service.render_ratio(15, 10), "0.2")
        self.assertEqual(service.render_ratio(-15, 10), "-0.2")

    def test_below_half_rounds_toward_zero(self):
        self.assertEqual(service.render_ratio(4, 10), "0.0")
        self.assertEqual(service.render_ratio(-4, 10), "0.0")
        self.assertEqual(service.render_ratio(24, 10), "0.2")

    def test_negative_zero_is_normalised(self):
        self.assertEqual(service.render_ratio(-1, 10), "0.0")
        self.assertEqual(service.render_ratio(0, -1), "0.0")

    def test_reading_and_mean_use_the_same_rule(self):
        self.assertEqual(service.render_reading(Fraction("1.25")), "1.3")
        self.assertEqual(service.render_reading(Fraction("-1.25")), "-1.3")
        self.assertEqual(service.render_mean(Fraction("0.1"), 2), "0.1")
        self.assertEqual(service.render_mean(Fraction("-0.1"), 2), "-0.1")


class FieldTests(unittest.TestCase):
    """The declared world: calendar-valid dates and plain decimal temperatures."""

    def test_dates(self):
        self.assertTrue(service.is_date("2024-01-01"))
        self.assertTrue(service.is_date("2024-02-29"))
        self.assertTrue(service.is_date("2024-01-01T10:00:00"))
        self.assertFalse(service.is_date("2023-02-29"))
        self.assertFalse(service.is_date("2024-13-01"))
        self.assertFalse(service.is_date("2024-1-1"))
        self.assertFalse(service.is_date("not-a-date"))
        self.assertFalse(service.is_date(""))

    def test_temperatures(self):
        self.assertTrue(service.is_temperature("10.4"))
        self.assertTrue(service.is_temperature("-2.5"))
        self.assertTrue(service.is_temperature("0"))
        self.assertFalse(service.is_temperature("1e3"))
        self.assertFalse(service.is_temperature("NaN"))
        self.assertFalse(service.is_temperature("Infinity"))
        self.assertFalse(service.is_temperature("+1.5"))
        self.assertFalse(service.is_temperature("1,5"))
        self.assertFalse(service.is_temperature(""))


class SummariseTests(unittest.TestCase):
    """The report is the declared framing, computed exactly."""

    def test_the_response_is_a_json_array_with_one_object_per_line(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,10.4\n"
            "2024-01-01,BRAVO,-2.5\n"
            "2024-01-02,ALPHA,11.6\n"
        )
        path = write_csv(text)
        try:
            body = service.summarise(path).decode("utf-8")
        finally:
            os.unlink(path)
        lines = body.splitlines()
        self.assertEqual(lines[0], "[")
        self.assertEqual(lines[-1], "]")
        self.assertEqual(len(lines), 9)
        self.assertEqual(
            lines[1],
            '{"station":"ALPHA","count":2,"min":10.4,"max":11.6,"mean":11.0}',
        )
        self.assertEqual(lines[2], ",")
        self.assertEqual(
            lines[3], '{"station":"BRAVO","count":1,"min":-2.5,"max":-2.5,"mean":-2.5}'
        )
        self.assertEqual(lines[4], ",")
        self.assertEqual(lines[5], '{"skipped":0}')
        self.assertEqual(lines[6], ",")
        self.assertEqual(lines[7], '{"total":3}')
        self.assertEqual(lines[-1], "]")
        document = json.loads(body)
        self.assertEqual(len(document), 4)
        self.assertEqual(document[0]["station"], "ALPHA")
        self.assertEqual(document[-1], {"total": 3})
        self.assertEqual(json.loads(body), report_lines(text))

    def test_every_line_matches_the_declared_shapes(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,10.4\n"
            "2024-01-01,BRAVO,-2.5\n"
            "oops\n"
        )
        path = write_csv(text)
        try:
            body = service.summarise(path).decode("utf-8")
        finally:
            os.unlink(path)
        station = re.compile(
            r'^\{"station":"[^"\\]*","count":[0-9]+,"min":-?[0-9]+\.[0-9],'
            r'"max":-?[0-9]+\.[0-9],"mean":-?[0-9]+\.[0-9]\},?$'
        )
        skipped = re.compile(r'^\{"skipped":[0-9]+\},?$')
        total = re.compile(r'^\{"total":[0-9]+\},?$')
        for line in body.splitlines():
            if line in ("[", "]", ","):
                continue
            self.assertTrue(
                station.match(line) or skipped.match(line) or total.match(line),
                "line matches no declared shape: %r" % line,
            )

    def test_malformed_rows_are_skipped_and_counted(self):
        path = write_csv("date,station,temperature_c\nnope\n2024-01-01,ALPHA,1.0\n")
        try:
            body = service.summarise(path).decode("utf-8")
        finally:
            os.unlink(path)
        self.assertIn('{"skipped":1}', body)
        self.assertIn('{"total":1}', body)

    def test_undecodable_bytes_are_skipped_and_never_abort_the_report(self):
        payload = (
            b"date,station,temperature_c\n"
            b"2024-01-01,ALPHA,1.0\n"
            b"2024-01-02,\xff\xfe,2.0\n"
            b"2024-01-03,ALPHA,3.0\n"
        )
        path = write_csv_bytes(payload)
        try:
            body = service.summarise(path).decode("utf-8")
        finally:
            os.unlink(path)
        self.assertIn('{"skipped":1}', body)
        self.assertIn('{"total":2}', body)
        self.assertIn('"count":2', body)

    def test_a_missing_file_raises_an_oserror(self):
        with self.assertRaises(OSError):
            service.summarise("/nonexistent/path/readings.csv")

    def test_main_rejects_a_bad_port(self):
        self.assertEqual(service.main(["station_summary.py", "x.csv", "abc"]), 2)
        self.assertEqual(service.main(["station_summary.py", "x.csv", "0"]), 2)
        self.assertEqual(service.main(["station_summary.py", "x.csv", "70000"]), 2)
        self.assertEqual(service.main(["station_summary.py"]), 2)


if __name__ == "__main__":
    unittest.main()
