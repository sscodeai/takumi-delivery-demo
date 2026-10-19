"""REQ-002: parsing the declared daily temperature CSV."""

import unittest

from helpers import HEADER, run_csv, skipped_of, total_of


class ParsingTests(unittest.TestCase):
    def test_declared_sample_is_aggregated_exactly(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-01,BRAVO,-2.5\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-02,BRAVO,-1.5\n"
            + "2024-01-03,ALPHA,9.5\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 3 9.5 11.6 10.5\n"
            "BRAVO 2 -2.5 -1.5 -2.0\n"
            "SKIPPED 0\n"
            "TOTAL 5\n",
        )

    def test_header_line_is_consumed_and_never_a_reading(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")
        self.assertNotIn("date ", result.stdout)

    def test_each_valid_row_counts_as_exactly_one_reading(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
            + "2024-01-04,BETA,4.0\n"
            + "2024-01-05,BETA,5.0\n"
        )
        result = run_csv(text)
        self.assertIn("ALPHA 3 1.0 3.0 2.0\n", result.stdout)
        self.assertIn("BETA 2 4.0 5.0 4.5\n", result.stdout)
        self.assertEqual(total_of(result.stdout), 5)
        self.assertEqual(skipped_of(result.stdout), 0)

    def test_header_is_resolved_by_column_name_not_position(self):
        text = "temperature_c,station,date\n19.5,Alpha,2020-01-01\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "Alpha 1 19.5 19.5 19.5\nSKIPPED 0\nTOTAL 1\n")

    def test_header_match_ignores_case_and_padding(self):
        text = " Date , Station , Temperature_C \n2020-01-01,Alpha,19.5\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "Alpha 1 19.5 19.5 19.5\nSKIPPED 0\nTOTAL 1\n")

    def test_a_first_line_that_is_not_the_declared_header_is_a_reading(self):
        # The declared world always carries the header, but the pipeline's own
        # sample declares the columns only in the document; a header-less first
        # line is a reading in the declared positional order, never dropped.
        text = (
            "2024-01-01,ALPHA,10.4\n"
            "2024-01-01,BRAVO,-2.5\n"
            "2024-01-02,ALPHA,11.6\n"
            "2024-01-02,BRAVO,-1.5\n"
            "2024-01-03,ALPHA,9.5\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 3 9.5 11.6 10.5\nBRAVO 2 -2.5 -1.5 -2.0\nSKIPPED 0\nTOTAL 5\n",
        )

    def test_calendar_valid_dates_are_accepted(self):
        for day in ("2024-01-01", "2024-02-29", "2023-12-31", "2024-12-31"):
            with self.subTest(day=day):
                result = run_csv(HEADER + "%s,ALPHA,1.0\n" % day)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")

    def test_a_date_with_a_time_suffix_is_accepted(self):
        result = run_csv(HEADER + "2024-01-01T08:30:00,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")

    def test_a_trailing_fragment_after_the_date_is_not_a_reading(self):
        # A permissive suffix match would wave ``2024-01-01 x`` through. The time
        # suffix is only valid when the whole field parses as an ISO-8601
        # datetime, so a calendar-valid prefix followed by garbage is malformed
        # and is skipped like any other bad date.
        text = (
            HEADER
            + "2024-01-01Tbogus,ALPHA,1.0\n"
            + "2024-01-01 x,ALPHA,1.0\n"
            + "2024-01-01T25:00:00,ALPHA,1.0\n"
            + "2024-01-01T08:30:00,ALPHA,2.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 2.0 2.0 2.0\nSKIPPED 3\nTOTAL 1\n")

    def test_impossible_and_malformed_dates_are_rejected(self):
        text = (
            HEADER
            + "2023-02-29,ALPHA,1.0\n"  # not a leap year
            + "2024-02-30,ALPHA,1.0\n"  # February has 29 days in 2024
            + "2024-13-01,ALPHA,1.0\n"  # month out of range
            + "2024-00-10,ALPHA,1.0\n"  # month zero
            + "2024-01-00,ALPHA,1.0\n"  # day zero
            + "2024-1-1,ALPHA,1.0\n"  # not zero padded
            + "not-a-date,ALPHA,1.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "SKIPPED 7\nTOTAL 0\n")

    def test_decimal_and_integer_temperatures_are_numeric(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10\n"
            + "2024-01-02,ALPHA,-3.5\n"
            + "2024-01-03,ALPHA,0.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertIn("ALPHA 3 -3.5 10.0 2.2\n", result.stdout)
        self.assertEqual(skipped_of(result.stdout), 0)

    def test_non_numeric_or_exotic_temperatures_are_rejected(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,abc\n"
            + "2024-01-01,ALPHA,NaN\n"
            + "2024-01-01,ALPHA,Infinity\n"
            + "2024-01-01,ALPHA,1e3\n"
            + "2024-01-01,ALPHA,+3\n"
            + "2024-01-01,ALPHA,.5\n"
            + "2024-01-01,ALPHA,-\n"
            + "2024-01-01,ALPHA,\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "SKIPPED 8\nTOTAL 0\n")

    def test_empty_station_is_rejected(self):
        text = HEADER + "2024-01-01,,1.0\n2024-01-01,ALPHA,2.0\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 2.0 2.0 2.0\nSKIPPED 1\nTOTAL 1\n")

    def test_wrong_field_counts_are_rejected(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA\n"
            + "2024-01-01,ALPHA,1.0,extra\n"
            + "2024-01-01,ALPHA,2.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 2.0 2.0 2.0\nSKIPPED 2\nTOTAL 1\n")

    def test_station_ids_are_case_sensitive(self):
        text = HEADER + "2024-01-01,Alpha,1.0\n2024-01-02,alpha,2.0\n"
        result = run_csv(text)
        self.assertIn("Alpha 1 1.0 1.0 1.0\n", result.stdout)
        self.assertIn("alpha 1 2.0 2.0 2.0\n", result.stdout)
        self.assertEqual(total_of(result.stdout), 2)

    def test_utf8_bom_and_crlf_are_accepted(self):
        text = "\ufeffdate,station,temperature_c\r\n2024-01-01,ALPHA,1.0\r\n2024-01-02,ALPHA,3.0\r\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 2 1.0 3.0 2.0\nSKIPPED 0\nTOTAL 2\n")
