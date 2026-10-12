"""REQ-003 / AMB-003 / DIFF-001: the aggregate is exact rational arithmetic.

The delivered summary.sh keeps temperatures as exact rationals and rounds with
integer arithmetic.  These deterministic fixtures pin the cases where binary
floating point or a lossy accumulator would disagree with the confirmed
half-away-from-zero rule, and where a float accumulator would drift on a long
run of readings.

Every expected string here was also produced by tests/reference.py, an
independent implementation that shares no code with summary.sh.
"""

import unittest

from helpers import HEADER, run_csv, station_lines, total_of
from reference import reference_output


class DeepDecimalRoundingTests(unittest.TestCase):
    def test_value_that_a_binary_float_would_round_the_wrong_way(self):
        # float("2.675") * 10 == 26.749999999999996, which truncates to 2.6;
        # the exact value is 26.75 and rounds half away from zero to 2.7.
        text = (
            HEADER
            + "2024-01-01,ALPHA,2.675\n"
            + "2024-01-02,BRAVO,0.575\n"
            + "2024-01-03,CHARLIE,-2.675\n"
            + "2024-01-04,DELTA,-0.575\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertIn("ALPHA 1 2.7 2.7 2.7\n", result.stdout)
        self.assertIn("BRAVO 1 0.6 0.6 0.6\n", result.stdout)
        self.assertIn("CHARLIE 1 -2.7 -2.7 -2.7\n", result.stdout)
        self.assertIn("DELTA 1 -0.6 -0.6 -0.6\n", result.stdout)

    def test_digits_beyond_the_third_decimal_still_decide_the_tie(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.24999\n"
            + "2024-01-02,ALPHA,1.25001\n"
            + "2024-01-03,BRAVO,-1.24999\n"
            + "2024-01-04,BRAVO,-1.25001\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        # ALPHA min 1.24999 -> 1.2, max 1.25001 -> 1.3, mean exactly 1.25 -> 1.3.
        self.assertIn("ALPHA 2 1.2 1.3 1.3\n", result.stdout)
        self.assertIn("BRAVO 2 -1.3 -1.2 -1.3\n", result.stdout)

    def test_positive_and_negative_mean_ties_round_away_from_zero(self):
        positive = run_csv(HEADER + "2024-01-01,ALPHA,0.2\n2024-01-02,ALPHA,0.3\n")
        self.assertIn("ALPHA 2 0.2 0.3 0.3\n", positive.stdout)
        negative = run_csv(HEADER + "2024-01-01,ALPHA,-0.2\n2024-01-02,ALPHA,-0.3\n")
        self.assertIn("ALPHA 2 -0.3 -0.2 -0.3\n", negative.stdout)

    def test_a_repeating_decimal_mean_is_exact_before_rounding(self):
        # 1.0 + 2.0 + 2.0 = 5.0, mean = 5/3 = 1.666... -> 1.7 half-up.
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,ALPHA,2.0\n"
        )
        result = run_csv(text)
        self.assertIn("ALPHA 3 1.0 2.0 1.7\n", result.stdout)


class ExactAccumulationTests(unittest.TestCase):
    def test_many_non_binary_readings_do_not_drift(self):
        # Forty readings of 0.1 are exactly 4.0, so the mean is exactly 0.1.
        text = HEADER + "".join(
            "2024-01-%02d,ALPHA,0.1\n" % (day % 28 + 1) for day in range(40)
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertIn("ALPHA 40 0.1 0.1 0.1\n", result.stdout)
        self.assertEqual(total_of(result.stdout), 40)

    def test_values_far_beyond_float_precision_stay_exact(self):
        # A sum a double cannot represent without loss; the mean is exactly .5.
        text = (
            HEADER
            + "2024-01-01,ALPHA,12345678901234567890\n"
            + "2024-01-02,ALPHA,12345678901234567891\n"
        )
        result = run_csv(text)
        self.assertIn(
            "ALPHA 2 12345678901234567890.0 12345678901234567891.0 "
            "12345678901234567890.5\n",
            result.stdout,
        )


class IndependentReferenceTests(unittest.TestCase):
    def test_a_deep_decimal_fixture_matches_the_independent_reference(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,2.675\n"
            + "2024-01-02,ALPHA,0.575\n"
            + "2024-01-03,ALPHA,-2.675\n"
            + "2024-01-04,BRAVO,1.24999\n"
            + "2024-01-05,BRAVO,1.25001\n"
            + "2024-01-06,BRAVO,0.05\n"
            + "2024-01-07,BRAVO,-0.05\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(station_lines(result.stdout), reference_output(text).splitlines()[:-2])
        self.assertEqual(result.stdout, reference_output(text))


if __name__ == "__main__":
    unittest.main()
