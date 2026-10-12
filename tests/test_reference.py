"""Self-tests for the independent reference implementation.

The reference is only useful if it is itself exact, so these tests pin its
rounding and aggregation behaviour with hand-computed values. They share no
code with summary.sh.
"""

import unittest
from fractions import Fraction

from reference import is_date, is_temperature, reference_lines, reference_output, round_half_up_one


class RoundingTests(unittest.TestCase):
    def test_half_away_from_zero(self):
        cases = {
            "1.25": "1.3",
            "-1.25": "-1.3",
            "0.05": "0.1",
            "-0.05": "-0.1",
            "1.24": "1.2",
            "-1.24": "-1.2",
            "0.0": "0.0",
            "-0.0": "0.0",
            "1.2499999": "1.2",
            "1.2500001": "1.3",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(round_half_up_one(Fraction(raw)), want)

    def test_exact_binary_sensitive_sevenths(self):
        # 1/7 = 0.142857... => 0.1; 3/7 = 0.4285... => 0.4; 5/7 => 0.7.
        self.assertEqual(round_half_up_one(Fraction(1, 7)), "0.1")
        self.assertEqual(round_half_up_one(Fraction(3, 7)), "0.4")
        self.assertEqual(round_half_up_one(Fraction(5, 7)), "0.7")
        self.assertEqual(round_half_up_one(Fraction(-5, 7)), "-0.7")


class ValidityTests(unittest.TestCase):
    def test_dates(self):
        for good in ("2024-01-01", "2024-02-29", "2024-01-01T08:00:00", "2024-01-01 08:00"):
            self.assertTrue(is_date(good), good)
        for bad in (
            "2023-02-29",
            "2024-02-30",
            "2024-13-01",
            "2024-1-1",
            "not-a-date",
            "",
            "2024-01-01Tbogus",
            "2024-01-01 x",
            "2024-01-01T25:00:00",
        ):
            self.assertFalse(is_date(bad), bad)

    def test_temperatures(self):
        for good in ("10", "10.4", "-2.5", "0.0", "-0"):
            self.assertTrue(is_temperature(good), good)
        for bad in ("abc", "NaN", "Infinity", "1e3", "+3", ".5", "-", ""):
            self.assertFalse(is_temperature(bad), bad)


class AggregationTests(unittest.TestCase):
    def test_sample_document_matches_the_requirement_sample(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,10.4\n"
            "2024-01-01,BRAVO,-2.5\n"
            "2024-01-02,ALPHA,11.6\n"
            "2024-01-02,BRAVO,-1.5\n"
            "2024-01-03,ALPHA,9.5\n"
        )
        self.assertEqual(
            reference_output(text),
            "ALPHA 3 9.5 11.6 10.5\nBRAVO 2 -2.5 -1.5 -2.0\nSKIPPED 0\nTOTAL 5\n",
        )

    def test_repeated_keys_merge(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,1.0\n"
            "2024-01-01,ALPHA,2.0\n"
        )
        self.assertEqual(reference_lines(text), ["ALPHA 2 1.0 2.0 1.5", "SKIPPED 0", "TOTAL 2"])

    def test_malformed_rows_are_counted_not_aggregated(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,ALPHA,1.0\n"
            "2024-01-01,ALPHA\n"
            "bad,ALPHA,2.0\n"
            "2024-01-01,ALPHA,xx\n"
        )
        self.assertEqual(reference_lines(text), ["ALPHA 1 1.0 1.0 1.0", "SKIPPED 3", "TOTAL 1"])

    def test_byte_wise_station_order(self):
        text = (
            "date,station,temperature_c\n"
            "2024-01-01,zeta,1.0\n"
            "2024-01-01,ALPHA,2.0\n"
            "2024-01-01,alpha,3.0\n"
        )
        self.assertEqual(
            reference_lines(text),
            ["ALPHA 1 2.0 2.0 2.0", "alpha 1 3.0 3.0 3.0", "zeta 1 1.0 1.0 1.0", "SKIPPED 0", "TOTAL 3"],
        )
