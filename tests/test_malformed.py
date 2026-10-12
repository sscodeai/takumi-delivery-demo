"""REQ-005 and AMB-001: malformed rows never abort and are counted."""

import unittest

from helpers import HEADER, run_csv, run_csv_bytes, skipped_of, station_lines, total_of


class MalformedTests(unittest.TestCase):
    def test_the_declared_malformed_fixture_completes_and_is_counted(self):
        # Exactly the malformed rows the requirement document declares in its
        # world: a short row, a non-numeric temperature and an unparseable date.
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-01,BRAVO,-2.5\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-02,BRAVO,-1.5\n"
            + "2024-01-03,ALPHA,9.5\n"
            + "2024-01-01,ALPHA\n"
            + "2024-01-01,ALPHA,abc\n"
            + "not-a-date,ALPHA,10.4\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertIn("ALPHA 3 9.5 11.6 10.5\n", result.stdout)
        self.assertIn("BRAVO 2 -2.5 -1.5 -2.0\n", result.stdout)
        self.assertEqual(skipped_of(result.stdout), 3)
        self.assertEqual(total_of(result.stdout), 5)

    def test_single_malformed_categories_are_each_skipped(self):
        cases = {
            "short-row": "2024-01-01,ALPHA\n",
            "long-row": "2024-01-01,ALPHA,1.0,extra\n",
            "empty-station": "2024-01-01,,1.0\n",
            "empty-row": "\n",
            "bad-date": "not-a-date,ALPHA,1.0\n",
            "impossible-date": "2024-02-30,ALPHA,1.0\n",
            "bad-temperature": "2024-01-01,ALPHA,abc\n",
            "empty-temperature": "2024-01-01,ALPHA,\n",
        }
        for name, row in cases.items():
            with self.subTest(case=name):
                result = run_csv(HEADER + row)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "SKIPPED 1\nTOTAL 0\n")

    def test_malformed_rows_never_change_a_valid_aggregate(self):
        valid = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,3.0\n"
            + "2024-01-03,BETA,5.0\n"
        )
        dirty = (
            valid
            + "2024-01-01,ALPHA\n"
            + "bad,ALPHA,9.0\n"
            + "2024-01-01,,7.0\n"
            + "2024-01-01,ALPHA,xx\n"
        )
        clean_result = run_csv(valid)
        dirty_result = run_csv(dirty)
        self.assertEqual(station_lines(clean_result.stdout), station_lines(dirty_result.stdout))
        self.assertEqual(total_of(clean_result.stdout), total_of(dirty_result.stdout))
        self.assertEqual(skipped_of(clean_result.stdout), 0)
        self.assertEqual(skipped_of(dirty_result.stdout), 4)

    def test_station_with_only_malformed_rows_has_no_station_line(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,BROKEN,abc\n"
            + "bad,BROKEN,1.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(station_lines(result.stdout), ["ALPHA 1 1.0 1.0 1.0"])
        self.assertEqual(skipped_of(result.stdout), 2)
        self.assertEqual(total_of(result.stdout), 1)

    def test_a_pathological_field_does_not_abort_the_run(self):
        huge = "9" * 5000
        text = HEADER + "2024-01-01,ALPHA,%s.5\n" % huge + "2024-01-02,ALPHA,1.0\n"
        result = run_csv(text, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(total_of(result.stdout), 2)
        self.assertEqual(skipped_of(result.stdout), 0)

    def test_undecodable_bytes_are_skipped_and_never_abort_the_run(self):
        # A readable CSV export is bytes, not guaranteed text: an undecodable
        # byte makes its record unparseable, so the record is skipped and
        # counted while the decodable records still aggregate. The process must
        # still exit 0, as REQ-001 promises for a readable input.
        payload = (
            (HEADER + "2024-01-01,ALPHA,1.0\n").encode("utf-8")
            + b"2024-01-02,\xff\xfe,2.0\n"
            + b"2024-01-03,ALPHA,3.0\n"
        )
        result = run_csv_bytes(payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 2 1.0 3.0 2.0\nSKIPPED 1\nTOTAL 2\n")

    def test_undecodable_bytes_in_the_date_field_are_skipped(self):
        # Where the bad byte lands does not matter: the record still cannot be
        # parsed, so it is counted among the skipped rows either way.
        payload = (HEADER + "2024-01-01,ALPHA,1.0\n").encode("utf-8") + b"\xff-01-02,ALPHA,2.0\n"
        result = run_csv_bytes(payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 1\nTOTAL 1\n")

    def test_an_undecodable_file_is_still_processed_to_completion(self):
        payload = b"\xff\xfe\xfd\n" + (HEADER + "2024-01-01,ALPHA,1.0\n").encode("utf-8")
        result = run_csv_bytes(payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 1\nTOTAL 1\n")
