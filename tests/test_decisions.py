"""AMB-002, AMB-003, DIFF-001 and REL-003: the confirmed decisions hold.

Each test below pins one option the human confirmed in
docs/requirements/intake.yaml, so an implementation that records a decision and
then does the opposite of it fails here, independently of the forged judge.
"""

import random
import unittest

from helpers import HEADER, run_csv, skipped_of, station_lines, total_of
from reference import reference_output, round_half_up_one

try:
    from fractions import Fraction
except ImportError:  # pragma: no cover - Fraction is standard library
    Fraction = None


class DuplicateResolutionTests(unittest.TestCase):
    """AMB-002 / REL-003: a repeated (date, station) row is its own reading."""

    def test_repeated_key_counts_every_occurrence(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,10.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 3 10.0 10.0 10.0\nSKIPPED 0\nTOTAL 3\n")

    def test_a_later_date_does_not_replace_an_earlier_one(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
            + "2024-01-04,ALPHA,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 4 1.0 4.0 2.5\nSKIPPED 0\nTOTAL 4\n")

    def test_every_occurrence_contributes_to_min_max_and_mean(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,5.0\n"
            + "2024-01-01,ALPHA,-3.0\n"
            + "2024-01-01,ALPHA,1.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 3 -3.0 5.0 1.0\nSKIPPED 0\nTOTAL 3\n")

    def test_duplicate_dates_across_stations_stay_separate(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,BRAVO,2.0\n"
            + "2024-01-01,ALPHA,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            result.stdout,
            "ALPHA 2 1.0 3.0 2.0\nBRAVO 1 2.0 2.0 2.0\nSKIPPED 0\nTOTAL 3\n",
        )


class HalfUpRoundingTests(unittest.TestCase):
    """AMB-003 / DIFF-001: round half away from zero to one decimal place."""

    def test_reference_and_tool_agree_on_ties(self):
        for value in ("1.25", "-1.25", "0.05", "-0.05", "2.35", "-2.35", "9.95"):
            with self.subTest(value=value):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % value)
                want = round_half_up_one(Fraction(value))
                self.assertEqual(
                    result.stdout,
                    "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want),
                )

    def test_plain_reading_is_exactly_the_selected_rule(self):
        # Trailing digits beyond one decimal place may only move the value up,
        # never toward zero: the confirmed option is half away from zero.
        text = HEADER + "2024-01-01,ALPHA,1.2501\n2024-01-02,ALPHA,-1.2501\n"
        result = run_csv(text)
        self.assertIn("ALPHA 2 -1.3 1.3 0.0\n", result.stdout)


class DifferentialTests(unittest.TestCase):
    """DIFF-001: an independent recomputation agrees with the printed report."""

    @staticmethod
    def _fixture(seed, rows=60):
        rng = random.Random(seed)
        stations = ["ALPHA", "BRAVO", "Charlie", "delta-9", "E1"]
        lines = [HEADER.rstrip("\n")]
        for _ in range(rows):
            day = rng.randint(1, 28)
            hour = rng.choice(["", "T00:00:00", " 12:30"])
            month = rng.randint(1, 12)
            station = rng.choice(stations)
            # Deliberately include 2- and 3-decimal values, ties included.
            value = rng.choice(
                [
                    "%.1f" % rng.uniform(-40, 45),
                    "%.2f" % rng.uniform(-40, 45),
                    "%.3f" % rng.uniform(-40, 45),
                    "1.25",
                    "-1.25",
                    "0.05",
                    "%d" % rng.randint(-40, 45),
                ]
            )
            lines.append("2024-%02d-%02d%s,%s,%s" % (month, day, hour, station, value))
        return "\n".join(lines) + "\n"

    def test_tool_matches_an_independent_implementation(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                text = self._fixture(seed)
                result = run_csv(text)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, reference_output(text))

    def test_malformed_rows_are_dropped_by_both_implementations(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "2024-13-01,ALPHA,2.0\n"
            + "2024-01-02,BRAVO,abc\n"
            + "2024-01-03,BRAVO,3.5\n"
            + "2024-01-03,,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, reference_output(text))
        self.assertEqual(skipped_of(result.stdout), 4)
        self.assertEqual(total_of(result.stdout), 2)


class AdditivityTests(unittest.TestCase):
    """REL-002 / AMB-005: the parts sum to TOTAL and TOTAL is valid-only."""

    def test_counts_sum_to_total_on_a_mixed_fixture(self):
        text = DifferentialTests._fixture(99, rows=200)
        result = run_csv(text)
        printed = sum(int(line.split(" ")[1]) for line in station_lines(result.stdout))
        self.assertEqual(printed, total_of(result.stdout))
        self.assertEqual(printed, sum(1 for line in text.splitlines()[1:] if len(line.split(",")) == 3))

    def test_total_ignores_malformed_rows(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,BRAVO,abc\n"
            + "2024-01-02,ALPHA,2.0\n"
        )
        result = run_csv(text)
        self.assertEqual(total_of(result.stdout), 2)
        self.assertEqual(skipped_of(result.stdout), 1)
