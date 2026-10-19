"""REQ-003, REQ-004, REQ-007 and AMB-003/AMB-004/AMB-005: the printed report."""

import unittest

from helpers import (
    HEADER,
    STATION_SHAPE,
    counts_sum,
    names_in_order,
    run_csv,
    skipped_of,
    station_lines,
    total_of,
)


class StationLineTests(unittest.TestCase):
    def test_shape_has_five_fields_with_single_spaces(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-03,BRAVO,-2.5\n"
        )
        result = run_csv(text)
        lines = station_lines(result.stdout)
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertRegex(line, STATION_SHAPE)
            self.assertNotIn("  ", line)
            self.assertEqual(len(line.split(" ")), 5)

    def test_count_min_max_mean_are_the_exact_aggregates(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,ALPHA,6.0\n"
            + "2024-01-04,BRAVO,-4.0\n"
            + "2024-01-05,BRAVO,-2.0\n"
        )
        result = run_csv(text)
        self.assertIn("ALPHA 3 1.0 6.0 3.0\n", result.stdout)
        self.assertIn("BRAVO 2 -4.0 -2.0 -3.0\n", result.stdout)

    def test_min_max_and_mean_each_carry_exactly_one_decimal_place(self):
        text = HEADER + "2024-01-01,ALPHA,1\n" + "2024-01-02,ALPHA,2.5\n"
        result = run_csv(text)
        self.assertIn("ALPHA 2 1.0 2.5 1.8\n", result.stdout)
        for token in station_lines(result.stdout)[0].split(" ")[2:]:
            self.assertRegex(token, r"^-?[0-9]+\.[0-9]$")

    def test_station_line_count_matches_the_number_of_valid_readings(self):
        text = HEADER + "".join(
            "2024-01-%02d,ALPHA,1.0\n" % day for day in range(1, 10)
        )
        result = run_csv(text)
        self.assertEqual(station_lines(result.stdout), ["ALPHA 9 1.0 1.0 1.0"])
        self.assertEqual(total_of(result.stdout), 9)

    def test_zero_and_negative_zero_render_as_zero_point_zero(self):
        text = HEADER + "2024-01-01,ALPHA,0.0\n2024-01-02,ALPHA,-0.0\n"
        result = run_csv(text)
        self.assertIn("ALPHA 2 0.0 0.0 0.0\n", result.stdout)
        self.assertNotIn("-0.0", result.stdout)

    def test_values_far_from_zero_keep_full_precision(self):
        text = HEADER + "2024-01-01,ALPHA,123456789.4\n2024-01-02,ALPHA,-123456789.6\n"
        result = run_csv(text)
        self.assertIn("ALPHA 2 -123456789.6 123456789.4 -0.1\n", result.stdout)


class RoundingTests(unittest.TestCase):
    """AMB-003: half away from zero to exactly one decimal place."""

    def test_single_reading_ties_round_away_from_zero(self):
        for raw, want in (
            ("1.25", "1.3"),
            ("1.24", "1.2"),
            ("-1.25", "-1.3"),
            ("-1.24", "-1.2"),
            ("0.05", "0.1"),
            ("-0.05", "-0.1"),
            ("-0.04", "0.0"),
        ):
            with self.subTest(raw=raw):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want))

    def test_mean_tie_rounds_away_from_zero(self):
        # 0.1 + 0.2 = 0.3 exactly; 0.3 / 2 = 0.15 => 0.2 half-up.
        positive = run_csv(HEADER + "2024-01-01,ALPHA,0.1\n2024-01-02,ALPHA,0.2\n")
        self.assertIn("ALPHA 2 0.1 0.2 0.2\n", positive.stdout)
        # -0.1 + -0.2 = -0.3 exactly; -0.3 / 2 = -0.15 => -0.2 half-up.
        negative = run_csv(HEADER + "2024-01-01,ALPHA,-0.1\n2024-01-02,ALPHA,-0.2\n")
        self.assertIn("ALPHA 2 -0.2 -0.1 -0.2\n", negative.stdout)

    def test_a_binary_float_would_get_this_wrong(self):
        # 0.2 + 0.2 + 0.2 + 0.2 + 0.2 = 1.0 exactly; the mean is 0.2, not
        # 0.20000000000000007 or a value that rounds to 0.2000000.
        text = HEADER + "".join(
            "2024-01-%02d,ALPHA,0.2\n" % day for day in range(1, 6)
        )
        result = run_csv(text)
        self.assertIn("ALPHA 5 0.2 0.2 0.2\n", result.stdout)

    def test_min_and_max_round_with_the_same_rule(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,-2.25\n"
            + "2024-01-02,ALPHA,2.25\n"
            + "2024-01-03,ALPHA,2.24\n"
        )
        result = run_csv(text)
        self.assertIn("ALPHA 3 -2.3 2.3 0.7\n", result.stdout)


class TotalLineTests(unittest.TestCase):
    """REQ-004 and AMB-005: exactly one TOTAL line counting valid readings."""

    def test_exactly_one_total_line_is_printed(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,BETA,2.0\n"
        result = run_csv(text)
        totals = [line for line in result.stdout.splitlines() if line.startswith("TOTAL ")]
        self.assertEqual(len(totals), 1)

    def test_total_is_the_sum_of_the_per_station_counts(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BETA,3.0\n"
            + "2024-01-04,GAMMA,4.0\n"
            + "2024-01-05,GAMMA,5.0\n"
        )
        result = run_csv(text)
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))
        self.assertEqual(total_of(result.stdout), 5)

    def test_malformed_rows_are_not_counted_in_the_total(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "not-a-date,BETA,2.0\n"
            + "2024-01-02,BETA,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(total_of(result.stdout), 2)
        self.assertEqual(counts_sum(result.stdout), 2)
        self.assertEqual(skipped_of(result.stdout), 1)


class OrderingTests(unittest.TestCase):
    """REQ-007 and AMB-004: ascending byte-wise station id order."""

    def test_station_lines_are_sorted_byte_wise_not_locale_wise(self):
        text = (
            HEADER
            + "2024-01-01,alpha,1.0\n"
            + "2024-01-02,Zulu,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
            + "2024-01-04,beta,4.0\n"
        )
        result = run_csv(text)
        # Byte-wise: ALPHA (0x41) < Zulu (0x5A) < alpha (0x61) < beta (0x62).
        self.assertEqual(names_in_order(result.stdout), ["ALPHA", "Zulu", "alpha", "beta", "SKIPPED", "TOTAL"])

    def test_non_ascii_ids_sort_by_utf8_bytes(self):
        text = (
            HEADER
            + "2024-01-01,zeta,1.0\n"
            + "2024-01-02,\u00e9psilon,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
        )
        result = run_csv(text)
        # UTF-8 bytes: ALPHA "A"=0x41 < "z"=0x7A < "\u00e9"=0xC3...
        self.assertEqual(names_in_order(result.stdout), ["ALPHA", "zeta", "\u00e9psilon", "SKIPPED", "TOTAL"])

    def test_the_report_ends_with_skipped_then_total(self):
        text = (
            HEADER
            + "2024-01-01,BETA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "not-a-date,GAMMA,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            names_in_order(result.stdout), ["ALPHA", "BETA", "SKIPPED", "TOTAL"]
        )
