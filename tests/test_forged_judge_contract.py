"""Lock the fixtures the external acceptance judge builds from the requirement.

The black-box judge for this delivery is forged from
`docs/requirements/intake.yaml` (ADR-026/ADR-033).  It does not read the
implementation.  It writes the declared header plus the declared sample, a
reversed copy of the sample, two duplicate fixtures (one with a later date and
one with an earlier date, each carrying a new maximum measure) and a fixture
with three malformed rows appended.  It then recomputes every expectation from
those fixtures itself, rounding half away from zero.

This suite reproduces those fixtures and pins the exact report the tool must
print for each of them, so a change that would fail the external judge fails the
delivered project's own CI first.  Nothing here imports the judge: the fixtures
and the expectations come from the requirement document's declared world.

  * REL-001  row-order-invariance      base vs reversed
  * REL-002  additivity                per-station counts sum to TOTAL
  * REL-003  duplicate-resolution      merge (AMB-002)
  * REL-004  malformed-row-accounting  skip-count (AMB-001)
  * DIFF-001 independent-aggregation   half away from zero (AMB-003)
"""

import unittest

from helpers import HEADER, counts_sum, run_csv, skipped_of, station_lines, total_of
from reference import reference_output

# The five data rows the requirement document declares in input_format.sample.
SAMPLE = [
    "2024-01-01,ALPHA,10.4",
    "2024-01-01,BRAVO,-2.5",
    "2024-01-02,ALPHA,11.6",
    "2024-01-02,BRAVO,-1.5",
    "2024-01-03,ALPHA,9.5",
]

BASE = HEADER + "\n".join(SAMPLE) + "\n"

# The judge's duplicate fixtures: the first sample row with a new maximum measure
# (12.6) and a date one day outside the sample's range on either side.
DUP_LATE = BASE + "2024-01-04,ALPHA,12.6\n"
DUP_EARLY = BASE + "2023-12-31,ALPHA,12.6\n"

# The judge's malformed fixture: a short row, a non-numeric measure and an
# unparseable date appended to the base fixture.
MALFORMED = (
    BASE
    + "2024-01-01,ALPHA\n"
    + "2024-01-01,ALPHA,abc\n"
    + "not-a-date,ALPHA,10.4\n"
)

# ALPHA {10.4, 11.6, 9.5}: count 3, min 9.5, max 11.6, mean 31.5/3 = 10.5.
# BRAVO {-2.5, -1.5}:       count 2, min -2.5, max -1.5, mean -4.0/2 = -2.0.
BASE_REPORT = "ALPHA 3 9.5 11.6 10.5\nBRAVO 2 -2.5 -1.5 -2.0\nSKIPPED 0\nTOTAL 5\n"

# With the duplicate row 12.6 the ALPHA mean is 44.1/4 = 11.025, which rounds
# half away from zero to 11.0 (the digit after the first decimal is 2).
DUP_REPORT = "ALPHA 4 9.5 12.6 11.0\nBRAVO 2 -2.5 -1.5 -2.0\nSKIPPED 0\nTOTAL 6\n"

# The three appended malformed rows never change a station aggregate.
MALFORMED_REPORT = "ALPHA 3 9.5 11.6 10.5\nBRAVO 2 -2.5 -1.5 -2.0\nSKIPPED 3\nTOTAL 5\n"


class ForgedJudgeFixtureTests(unittest.TestCase):
    def test_base_fixture_report_is_exact(self):
        result = run_csv(BASE)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, BASE_REPORT)
        self.assertNotIn("date ", result.stdout)

    def test_reversed_sample_is_byte_identical(self):
        result = run_csv(HEADER + "\n".join(reversed(SAMPLE)) + "\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, BASE_REPORT)

    def test_duplicate_fixtures_merge_every_occurrence(self):
        for name, fixture in (("late-date", DUP_LATE), ("early-date", DUP_EARLY)):
            with self.subTest(fixture=name):
                result = run_csv(fixture)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, DUP_REPORT)
                self.assertEqual(total_of(result.stdout), 6)
                self.assertEqual(skipped_of(result.stdout), 0)

    def test_malformed_fixture_completes_and_reports_the_count(self):
        result = run_csv(MALFORMED)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, MALFORMED_REPORT)
        self.assertEqual(skipped_of(result.stdout), 3)
        self.assertEqual(total_of(result.stdout), 5)

    def test_expected_values_agree_with_the_independent_reference(self):
        for name, fixture in (
            ("base", BASE),
            ("dup-late", DUP_LATE),
            ("dup-early", DUP_EARLY),
            ("malformed", MALFORMED),
        ):
            with self.subTest(fixture=name):
                result = run_csv(fixture)
                self.assertEqual(result.stdout, reference_output(fixture))

    def test_additivity_holds_on_every_fixture(self):
        for name, fixture in (
            ("base", BASE),
            ("dup-late", DUP_LATE),
            ("malformed", MALFORMED),
        ):
            with self.subTest(fixture=name):
                result = run_csv(fixture)
                self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))

    def test_malformed_rows_leave_the_station_lines_untouched(self):
        clean = run_csv(BASE)
        dirty = run_csv(MALFORMED)
        self.assertEqual(station_lines(dirty.stdout), station_lines(clean.stdout))


class DeclaredSampleTests(unittest.TestCase):
    """The document's sample has no header: it is the judge's starting world."""

    def test_header_less_sample_is_aggregated(self):
        result = run_csv("\n".join(SAMPLE) + "\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, BASE_REPORT)

    def test_header_less_sample_matches_the_independent_reference(self):
        text = "\n".join(SAMPLE) + "\n"
        self.assertEqual(run_csv(text).stdout, reference_output(text))


if __name__ == "__main__":
    unittest.main()
