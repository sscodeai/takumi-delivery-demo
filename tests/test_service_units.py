"""Unit tests for the service's aggregation primitives and report assembly.

These tests import ``station_service`` directly and exercise the pure helpers
(``render_ratio``, ``render_reading``, ``render_mean``, ``is_date``,
``is_temperature``) plus ``summarise`` and ``main`` at the function boundary.
The process-boundary HTTP tests live in ``test_service.py``; together they cover
the unit and integration halves of the requirement document.
"""

import json
import os
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import station_service as service  # noqa: E402 - path set above


def duration(value):
    """Write ``value`` to a temporary CSV and return the path.

    The caller owns the file and must remove it when done.
    """
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    try:
        handle.write(value)
        handle.close()
        return handle.name
    except BaseException:
        handle.close()
        os.unlink(handle.name)
        raise


def report_lines(text):
    """Summarise ``text`` and return the JSON objects it reports."""
    path = duration(text)
    try:
        body = service.summarise(path).decode("utf-8")
    finally:
        os.unlink(path)
    return [json.loads(line) for line in body.splitlines() if line.strip()]


class RenderRatioTests(unittest.TestCase):
    """AMB-003 at its narrowest: ``render_ratio`` takes tenths and rounds half up.

    The numerator/denominator pair is already scaled by ten (``render_reading``
    and ``render_mean`` do that scaling), so ``render_ratio(125, 10)`` is 12.5
    tenths and rounds to 1.3 units.
    """

    def test_exact_values_carry_one_decimal(self):
        self.assertEqual(service.render_ratio(100, 1), "10.0")
        self.assertEqual(service.render_ratio(10, 1), "1.0")
        self.assertEqual(service.render_ratio(0, 1), "0.0")
        self.assertEqual(service.render_ratio(5, 1), "0.5")

    def test_half_rounds_away_from_zero(self):
        self.assertEqual(service.render_ratio(125, 10), "1.3")
        self.assertEqual(service.render_ratio(-125, 10), "-1.3")
        self.assertEqual(service.render_ratio(15, 10), "0.2")
        self.assertEqual(service.render_ratio(-15, 10), "-0.2")

    def test_just_below_half_rounds_down(self):
        self.assertEqual(service.render_ratio(124, 10), "1.2")
        self.assertEqual(service.render_ratio(-124, 10), "-1.2")

    def test_negative_zero_is_normalised(self):
        self.assertEqual(service.render_ratio(-1, 100), "0.0")

    def test_sign_follows_the_ratio(self):
        self.assertEqual(service.render_ratio(5, 1), "0.5")
        self.assertEqual(service.render_ratio(-5, 1), "-0.5")
        self.assertEqual(service.render_ratio(5, -1), "-0.5")
        self.assertEqual(service.render_ratio(-5, -1), "0.5")


class RenderFractionTests(unittest.TestCase):
    """The reading and mean renderers build on exact Fraction arithmetic."""

    def test_reading_renders_half_up(self):
        self.assertEqual(service.render_reading(Fraction("1.25")), "1.3")
        self.assertEqual(service.render_reading(Fraction("-1.25")), "-1.3")
        self.assertEqual(service.render_reading(Fraction("1")), "1.0")

    def test_mean_renders_half_up(self):
        values = [Fraction("0.1"), Fraction("0.2")]
        self.assertEqual(service.render_mean(sum(values), len(values)), "0.2")
        negatives = [Fraction("-0.1"), Fraction("-0.2")]
        self.assertEqual(service.render_mean(sum(negatives), len(negatives)), "-0.2")
        self.assertEqual(service.render_mean(Fraction(1), 3), "0.3")


class FieldValidationTests(unittest.TestCase):
    """REQ-003: what makes a date and a temperature well formed."""

    def test_valid_dates(self):
        for text in ("2024-01-01", "2024-02-29", "1999-12-31", "2024-01-01T12:00:00"):
            with self.subTest(text=text):
                self.assertTrue(service.is_date(text))

    def test_invalid_dates(self):
        for text in ("2024-02-30", "2023-02-29", "2024-13-01", "2024-00-01",
                     "2024-1-01", "not-a-date", ""):
            with self.subTest(text=text):
                self.assertFalse(service.is_date(text))

    def test_valid_temperatures(self):
        for text in ("0", "-0", "10.4", "-2.5", "007", "12345678901234567890"):
            with self.subTest(text=text):
                self.assertTrue(service.is_temperature(text))

    def test_invalid_temperatures(self):
        for text in ("abc", "", "1.2.3", "1e3", "+1.0", "1,5", "nan", "inf"):
            with self.subTest(text=text):
                self.assertFalse(service.is_temperature(text))


class SummariseUnitTests(unittest.TestCase):
    """REQ-003/004/005 at the function boundary, before the HTTP surface."""

    def test_sample_report(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,10.4\n"
            "2024-01-01,BRAVO,-2.5\n"
            "2024-01-02,ALPHA,11.6\n"
            "2024-01-02,BRAVO,-1.5\n"
            "2024-01-03,ALPHA,9.5\n"
        )
        self.assertEqual(
            report_lines(text),
            [
                {"station": "ALPHA", "count": 3, "min": 9.5, "max": 11.6, "mean": 10.5},
                {"station": "BRAVO", "count": 2, "min": -2.5, "max": -1.5, "mean": -2.0},
                {"skipped": 0},
                {"total": 5},
            ],
        )

    def test_malformed_rows_are_counted_not_aggregated(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,1.0\n"
            "2024-01-01,ALPHA\n"
            "bad,ALPHA,2.0\n"
            "2024-02-30,ALPHA,2.0\n"
            "2024-01-01,ALPHA,abc\n"
        )
        self.assertEqual(
            report_lines(text),
            [
                {"station": "ALPHA", "count": 1, "min": 1.0, "max": 1.0, "mean": 1.0},
                {"skipped": 4},
                {"total": 1},
            ],
        )

    def test_repeated_keys_merge_each_occurrence(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,5.0\n"
            "2024-01-01,ALPHA,-3.0\n"
            "2024-01-01,ALPHA,1.0\n"
        )
        self.assertEqual(
            report_lines(text),
            [
                {"station": "ALPHA", "count": 3, "min": -3.0, "max": 5.0, "mean": 1.0},
                {"skipped": 0},
                {"total": 3},
            ],
        )

    def test_empty_input_reports_zero(self):
        self.assertEqual(report_lines(""), [{"skipped": 0}, {"total": 0}])


class MainUnitTests(unittest.TestCase):
    """REQ-002: the start command validates its arguments before serving."""

    def test_usage_error_without_arguments(self):
        self.assertEqual(service.main(["station_service.py"]), 2)

    def test_non_numeric_port_is_rejected(self):
        path = duration("date,station,temperature_c\n")
        try:
            self.assertEqual(
                service.main(["station_service.py", path, "not-a-port"]), 2
            )
        finally:
            os.unlink(path)

    def test_out_of_range_port_is_rejected(self):
        path = duration("date,station,temperature_c\n")
        try:
            self.assertEqual(service.main(["station_service.py", path, "0"]), 2)
            self.assertEqual(service.main(["station_service.py", path, "70000"]), 2)
        finally:
            os.unlink(path)

    def test_unreadable_input_reports_failure(self):
        missing = os.path.join(ROOT, "does-not-exist-unit.csv")
        self.assertEqual(service.main(["station_service.py", missing, "9"]), 1)


if __name__ == "__main__":
    unittest.main()
