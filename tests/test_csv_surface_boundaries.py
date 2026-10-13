"""CSV-surface and boundary coverage for the delivered ``summary.sh``.

The focused suites pin the declared contract; this module covers the CSV
mechanisms the requirement's "CSV export" wording implies but the other suites
leave implicit:

* RFC 4180 quoting -- a quoted field is one field even when it contains the
  delimiter, and the surrounding quotes are removed before the field is
  validated (REQ-002);
* a UTF-8 byte-order mark or CRLF endings on a header-less first row, because
  the document's declared sample carries no header (REQ-002);
* the smallest possible report -- a single reading -- so count/min/max/mean
  collapse to the reading while the SKIPPED/TOTAL trailer stays exact
  (REQ-003, REQ-004).

Every test drives the real entry point (``bash summary.sh <csv>``) through a
process boundary.  Expectations that can be recomputed from the printed report
(additivity, the one-decimal shape) are recomputed rather than transcribed.
"""

import unittest

from helpers import (
    HEADER,
    counts_sum,
    run_csv,
    skipped_of,
    station_lines,
    total_of,
)


class CsvQuotingTests(unittest.TestCase):
    """REQ-002: the declared input is CSV, so quoting is part of the surface."""

    def test_quoted_fields_are_unwrapped_before_validation(self):
        # The declared world has no quoting, but a CSV export may quote any
        # field.  The quotes are syntax, not value: a quoted station, date and
        # temperature must be read exactly like their bare spellings.
        text = (
            HEADER
            + '2024-01-01,"ALPHA",1.5\n'
            + '"2024-01-02",ALPHA,"3.5"\n'
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 2 1.5 3.5 2.5\nSKIPPED 0\nTOTAL 2\n",
        )
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))

    def test_a_quoted_station_id_containing_a_comma_is_one_field(self):
        # The embedded comma is data, not a field separator, so the row is not a
        # wrong-field-count row: nothing is skipped and the station keeps two
        # readings.
        text = (
            HEADER
            + '2024-01-01,"ALPHA,WEST",1.0\n'
            + '2024-01-02,"ALPHA,WEST",3.0\n'
            + "2024-01-03,BRAVO,2.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(skipped_of(result.stdout), 0)
        self.assertEqual(total_of(result.stdout), 3)
        self.assertEqual(len(station_lines(result.stdout)), 2)
        quoted = next(
            line
            for line in station_lines(result.stdout)
            if line.startswith("ALPHA,WEST")
        )
        self.assertEqual(quoted.split(" ")[1:], ["2", "1.0", "3.0", "2.0"])

    def test_quoted_temperature_and_date_values_parse_as_plain_values(self):
        quoted = run_csv(HEADER + '2024-01-01,ALPHA,"-2.5"\n')
        bare = run_csv(HEADER + "2024-01-01,ALPHA,-2.5\n")
        self.assertEqual(quoted.returncode, 0)
        self.assertEqual(quoted.stdout, bare.stdout)
        self.assertEqual(quoted.stdout, "ALPHA 1 -2.5 -2.5 -2.5\nSKIPPED 0\nTOTAL 1\n")


class EncodingBoundaryTests(unittest.TestCase):
    """REQ-002: encoding artifacts never corrupt a field before validation."""

    def test_a_bom_on_a_header_less_first_row_is_not_part_of_the_station(self):
        # The declared sample has no header line.  A UTF-8 BOM on that first row
        # must not turn the date into an unparseable value or the station id into
        # "\ufeffALPHA".
        text = "\ufeff2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,3.0\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 2 1.0 3.0 2.0\nSKIPPED 0\nTOTAL 2\n",
        )

    def test_crlf_endings_on_a_header_less_first_row_are_consumed(self):
        text = "2024-01-01,ALPHA,1.0\r\n2024-01-02,ALPHA,3.0\r\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 2 1.0 3.0 2.0\nSKIPPED 0\nTOTAL 2\n",
        )


class SmallestReportTests(unittest.TestCase):
    """REQ-003 and REQ-004: the boundary case of exactly one reading."""

    def test_a_single_reading_collapses_to_its_own_rounded_value(self):
        text = HEADER + "2024-06-15,ONLY,-0.05\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        # count 1; min == max == mean == the reading, half away from zero.
        self.assertEqual(
            result.stdout,
            "ONLY 1 -0.1 -0.1 -0.1\nSKIPPED 0\nTOTAL 1\n",
        )
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))

    def test_a_single_station_with_a_single_integer_reading(self):
        text = HEADER + "2024-06-15,ONLY,7\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ONLY 1 7.0 7.0 7.0\nSKIPPED 0\nTOTAL 1\n",
        )


if __name__ == "__main__":
    unittest.main()
