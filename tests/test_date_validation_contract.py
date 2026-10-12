"""Unit and integration tests for the previous step's date-validation fix.

The previous step changed ``is_date`` in three places at once:

* the delivered CLI, the inline Python inside ``summary.sh``;
* the delivered HTTP service, ``station_summary.py``;
* the independent oracle, ``tests/reference.py``.

Before the fix a calendar-valid prefix followed by anything was accepted, so a
mangled row such as ``2024-01-01 x`` or ``2024-01-01Tbogus`` was counted as a
real reading.  After the fix a time suffix is valid only when the whole field
parses as an ISO-8601 datetime, so those rows are malformed and follow the
confirmed skip-count decision.

This module is the unit and integration layer for that fix.  It pins the
acceptance criteria and the confirmed ambiguity decisions the fix can affect:

  * REQ-002  a row is a reading only when its date parses;
  * REQ-003  the station aggregate stays exact after the rejected rows;
  * REQ-004  exactly one TOTAL line;
  * REQ-005  a malformed date is skipped, never aborts, and is counted;
  * REQ-006  the result depends only on the multiset of rows;
  * REL-001  row-order invariance with the rejected rows present;
  * REL-004  malformed-row accounting (AMB-001);
  * AMB-001  skip-count: rejected rows appear on the ``SKIPPED`` line only;
  * AMB-002  merge: the fix must not collapse repeated (date, station) keys;
  * AMB-003  half-up: the aggregates still round half away from zero;
  * AMB-004  ascending byte-wise station order is unchanged;
  * AMB-005  TOTAL counts valid readings only, so rejected rows leave it alone.

The service surface had no trailing-fragment test after the fix; the unit case
below and the HTTP integration case in ``test_service.py`` close that gap, and
the CLI cases here pin the same behaviour at the delivered boundary.
"""

import json
import os
import sys
import tempfile
import unittest

from helpers import HEADER, run_csv, skipped_of, station_lines, total_of
from reference import is_date as reference_is_date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import station_summary as service  # noqa: E402 - path set above

# Fields the declared world accepts: a calendar-valid ISO-8601 date, optionally
# followed by a time suffix that parses as an ISO-8601 datetime.
GOOD_DATES = [
    "2024-01-01",
    "2024-02-29",
    "2024-12-31",
    "2024-01-01T00:00:00",
    "2024-01-01 08:00",
    "2024-01-01T08:30:00",
    "2024-01-01T08:00:00.123456",
    "2024-01-01T08:00:00+09:00",
    "2024-01-01T08:00:00Z",
]

# Fields the declared world rejects.  The trailing-fragment and
# impossible-time entries near the end are the regression the previous step
# fixed: a real calendar date with a trailing fragment or an impossible time
# that the old permissive suffix match waved through.
BAD_DATES = [
    "2023-02-29",  # not a leap year
    "2024-02-30",  # February has 29 days in 2024
    "2024-13-01",  # month out of range
    "2024-00-10",  # month zero
    "2024-01-00",  # day zero
    "2024-1-1",  # not zero padded
    "not-a-date",
    "",
    "2024-01-01Tbogus",  # trailing garbage after T
    "2024-01-01 x",  # trailing garbage after a space
    "2024-01-01T25:00:00",  # impossible hour
    "2024-01-01T08:00:00xyz",  # trailing garbage after a time
    "2024-01-01 ",  # trailing space, no time
    "2024-01-01T",  # dangling time marker
]


def cli_acceptance(values):
    """Classify ``values`` as dates by running the delivered CLI.

    Each candidate is a single row with its own station id, so a station line
    proves the date was accepted and the SKIPPED count proves it was rejected.
    Returns ``{index: accepted?}`` keyed by position.
    """
    rows = ["%s,ST%03d,1.0" % (value, index) for index, value in enumerate(values)]
    result = run_csv(HEADER + "\n".join(rows) + "\n")
    if result.returncode != 0:
        raise AssertionError("summary.sh failed: %s" % result.stderr)
    accepted = {
        int(line.split(" ")[0][2:]) for line in station_lines(result.stdout)
    }
    return {index: index in accepted for index in range(len(values))}


class SharedDatePredicateTests(unittest.TestCase):
    """The fix must be identical in the CLI, the service and the oracle."""

    def test_the_oracle_and_the_service_agree_on_every_boundary(self):
        for value in GOOD_DATES + BAD_DATES:
            expected = value in GOOD_DATES
            with self.subTest(value=value):
                self.assertEqual(reference_is_date(value), expected)
                self.assertEqual(service.is_date(value), expected)

    def test_the_cli_agrees_with_the_oracle_and_the_service(self):
        values = GOOD_DATES + BAD_DATES
        cli = cli_acceptance(values)
        for index, value in enumerate(values):
            with self.subTest(value=value):
                expected = value in GOOD_DATES
                self.assertEqual(cli[index], expected)
                self.assertEqual(cli[index], reference_is_date(value))
                self.assertEqual(cli[index], service.is_date(value))

    def test_the_regression_fields_are_rejected_by_all_three(self):
        # The exact inputs the old permissive suffix match accepted.  Each one
        # must be malformed in the CLI, the service and the oracle.
        for value in ("2024-01-01Tbogus", "2024-01-01 x", "2024-01-01T25:00:00"):
            with self.subTest(value=value):
                self.assertFalse(reference_is_date(value))
                self.assertFalse(service.is_date(value))
        cli = cli_acceptance(list(("2024-01-01Tbogus", "2024-01-01 x", "2024-01-01T25:00:00")))
        self.assertEqual(cli, {0: False, 1: False, 2: False})


class CliIntegrationTests(unittest.TestCase):
    """REQ-002/REQ-005/AMB-001: the fix through the delivered CLI."""

    def test_a_trailing_fragment_is_skipped_and_counted(self):
        # Three mangled variants of a real date plus one genuine datetime.  Only
        # the datetime is a reading; the other three are malformed rows on the
        # SKIPPED line (AMB-001 skip-count), excluded from every aggregate.
        text = (
            HEADER
            + "2024-01-01Tbogus,ALPHA,1.0\n"
            + "2024-01-01 x,ALPHA,1.0\n"
            + "2024-01-01T25:00:00,ALPHA,1.0\n"
            + "2024-01-01T08:30:00,ALPHA,2.0\n"
            + "2024-01-02,ALPHA,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 2 2.0 3.0 2.5\nSKIPPED 3\nTOTAL 2\n",
        )

    def test_a_valid_time_suffix_is_still_a_reading(self):
        # The fix tightened the suffix, it did not forbid it: a full ISO-8601
        # datetime stays a valid reading in the CLI.
        text = (
            HEADER
            + "2024-01-01T08:30:00,ALPHA,1.0\n"
            + "2024-01-01 08:30,ALPHA,2.0\n"
            + "2024-01-02T00:00:00.500000,ALPHA,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 3 1.0 3.0 2.0\nSKIPPED 0\nTOTAL 3\n",
        )

    def test_the_fix_does_not_collapse_repeated_date_station_keys(self):
        # AMB-002 merge: the rejected row must not change how the two valid
        # occurrences of the same (date, station) key are aggregated.
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,20.0\n"
            + "2024-01-01Tbad,ALPHA,99.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 2 10.0 20.0 15.0\nSKIPPED 1\nTOTAL 2\n",
        )

    def test_the_aggregates_still_round_half_away_from_zero(self):
        # AMB-003 half-up: a rejected row must not perturb the exact rational
        # aggregate of the accepted rows.
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.25\n"
            + "2024-01-01Tbad,ALPHA,0.0\n"
            + "2024-01-02,ALPHA,1.25\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 2 1.3 1.3 1.3\nSKIPPED 1\nTOTAL 2\n",
        )

    def test_total_counts_valid_readings_only(self):
        # AMB-005: the three malformed rows never reach TOTAL.
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01 x,BRAVO,2.0\n"
            + "2024-01-01Tbogus,BRAVO,3.0\n"
            + "2024-01-02,BRAVO,4.0\n"
            + "2024-01-01T25:00:00,CHARLIE,5.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(skipped_of(result.stdout), 3)
        self.assertEqual(total_of(result.stdout), 2)
        self.assertEqual(station_lines(result.stdout), ["ALPHA 1 1.0 1.0 1.0", "BRAVO 1 4.0 4.0 4.0"])

    def test_rejected_rows_do_not_change_the_row_order_invariance(self):
        # REL-001: the output must depend only on the multiset of rows, so
        # shuffling the fixture with its rejected rows yields identical output.
        rows = [
            "2024-01-01,ALPHA,10.4",
            "2024-01-01 x,BRAVO,-2.5",
            "2024-01-02,ALPHA,11.6",
            "2024-01-01Tbogus,BRAVO,-1.5",
            "2024-01-03,ALPHA,9.5",
        ]
        straight = run_csv(HEADER + "\n".join(rows) + "\n")
        reversed_rows = run_csv(HEADER + "\n".join(reversed(rows)) + "\n")
        self.assertEqual(straight.stdout, reversed_rows.stdout)
        self.assertIn("SKIPPED 2\n", straight.stdout)
        self.assertEqual(total_of(straight.stdout), 3)

    def test_rejected_rows_leave_station_lines_untouched(self):
        # REQ-003/REL-004: the malformed rows never produce a station line and
        # never change a count, min, max or mean.
        clean = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,3.0\n"
        dirty = clean + "2024-01-03 x,ALPHA,99.0\n2024-01-04Tbad,ALPHA,-99.0\n"
        clean_result = run_csv(clean)
        dirty_result = run_csv(dirty)
        self.assertEqual(station_lines(clean_result.stdout), station_lines(dirty_result.stdout))
        self.assertEqual(station_lines(dirty_result.stdout), ["ALPHA 2 1.0 3.0 2.0"])
        self.assertEqual(skipped_of(dirty_result.stdout), 2)


class ServiceUnitTests(unittest.TestCase):
    """Unit tests for the fix in ``station_summary`` (the HTTP artifact)."""

    def test_summarise_skips_a_trailing_fragment(self):
        text = (
            HEADER
            + "2024-01-01Tbogus,ALPHA,1.0\n"
            + "2024-01-01 x,ALPHA,1.0\n"
            + "2024-01-01T25:00:00,ALPHA,1.0\n"
            + "2024-01-01T08:30:00,ALPHA,2.0\n"
        )
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        handle.write(text)
        handle.close()
        try:
            document = json.loads(service.summarise(handle.name).decode("utf-8"))
        finally:
            os.unlink(handle.name)
        self.assertEqual(
            document,
            [
                {"station": "ALPHA", "count": 1, "min": 2.0, "max": 2.0, "mean": 2.0},
                {"skipped": 3},
                {"total": 1},
            ],
        )


if __name__ == "__main__":
    unittest.main()
