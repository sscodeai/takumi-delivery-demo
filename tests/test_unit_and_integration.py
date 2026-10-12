"""Unit and integration tests for the delivered ``summary.sh``.

This module is the unit-and-integration layer for the implementation the
previous step delivered: the command-line tool ``summary.sh`` described by
``docs/requirements/intake.yaml`` (``bash summary.sh <csv>``).

It covers every REQ-nnn acceptance criterion and every AMB-nnn decision the
confirmed document records, and it exercises them at two levels:

* **Unit** -- the embedded Python implementation is loaded from the ``<<'PY'``
  heredoc of ``summary.sh`` and its pure functions and ``aggregate`` helper are
  tested directly.  This pins parsing, rounding, ``SKIPPED`` accounting and
  station ordering without paying for a subprocess per assertion.
* **Integration** -- the same contract is checked through the real process
  boundary (``bash summary.sh <csv>``) on the document's declared sample,
  fixtures holding every malformed row class, shuffled permutations and a
  two-hundred-thousand-row year, and a second run is made with the network
  disabled.  The values are compared with the independent reference in
  ``tests/reference.py`` wherever an expectation can be recomputed instead of
  hand-copied.

Traceability:

    REQ-001 entry point and $1       EntryPointIntegrationTests
    REQ-002 CSV parsing              ParsingIntegrationTests, EmbeddedUnitTests
    REQ-003 per-station aggregates   AggregateIntegrationTests, EmbeddedUnitTests
    REQ-004 total line               AggregateIntegrationTests
    REQ-005 malformed rows           MalformedIntegrationTests, EmbeddedUnitTests
    REQ-006 order independence       OrderingIntegrationTests
    REQ-007 station ordering         OrderingIntegrationTests, EmbeddedUnitTests
    REQ-008 offline operation        OfflineIntegrationTests
    REQ-009 year of readings         PerformanceIntegrationTests
    AMB-001 skip-count               MalformedIntegrationTests
    AMB-002 merge                    AmbiguityDecisionTests
    AMB-003 half-up                  AmbiguityDecisionTests, EmbeddedUnitTests
    AMB-004 ascending byte-wise      OrderingIntegrationTests
    AMB-005 valid-only TOTAL         AmbiguityDecisionTests
    REL-001..REL-004                 OrderingIntegrationTests, AmbiguityDecisionTests
    DIFF-001 independent aggregation AmbiguityDecisionTests
"""

import os
import random
import re
import subprocess
import tempfile
import time
import unittest
from fractions import Fraction

from helpers import (
    HEADER,
    ROOT,
    SCRIPT,
    counts_sum,
    names_in_order,
    run_csv,
    skipped_of,
    station_lines,
    total_of,
)
from reference import reference_output, round_half_up_one

DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")

# ``<station> <count> <min> <max> <mean>`` with single spaces and exactly one
# digit after every decimal point (REQ-003).
STATION_SHAPE = re.compile(
    r"^\S+ [0-9]+ -?[0-9]+\.[0-9] -?[0-9]+\.[0-9] -?[0-9]+\.[0-9]$"
)


def load_embedded_implementation():
    """Execute the Python embedded in ``summary.sh`` in a private namespace.

    The script feeds its heredoc to ``python3`` on stdin, so the exact code the
    process runs is the text between ``<<'PY'`` and the closing ``PY``.  Loading
    it here lets the unit tests call the real parsing, rounding and aggregation
    helpers rather than a re-implementation.
    """
    with open(SCRIPT, encoding="utf-8") as handle:
        source = handle.read()
    marker = "<<'PY'\n"
    start = source.index(marker) + len(marker)
    end = source.rindex("\nPY\n")
    code = source[start:end]
    namespace = {"__name__": "summary_under_test"}
    exec(compile(code, SCRIPT, "exec"), namespace)
    return namespace


IMPL = load_embedded_implementation()


def write_temp_csv(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    handle.write(text)
    handle.close()
    return handle.name


class EmbeddedUnitTests(unittest.TestCase):
    """Unit tests against the pure functions inside summary.sh."""

    def test_the_embedded_module_exposes_the_contracted_helpers(self):
        for name in (
            "is_date",
            "is_temperature",
            "render_one_decimal",
            "render_reading",
            "render_mean",
            "aggregate",
        ):
            with self.subTest(name=name):
                self.assertTrue(callable(IMPL[name]))

    def test_date_validation_accepts_calendar_dates_only(self):
        # REQ-002: a parseable date.  A calendar-invalid month or day is not.
        for good in ("2024-01-01", "2024-02-29", "1999-12-31"):
            with self.subTest(good=good):
                self.assertTrue(IMPL["is_date"](good))
        for bad in (
            "2024-13-01",
            "2024-02-30",
            "2024-1-1",
            "20240101",
            "not-a-date",
            "",
            "2024-01-01 x",
        ):
            with self.subTest(bad=bad):
                self.assertFalse(IMPL["is_date"](bad))

    def test_temperature_validation_accepts_plain_decimals_only(self):
        # REQ-002: a numeric temperature_c.  Exponential, NaN and blank
        # representations are not numeric in a CSV export.
        for good in ("10.4", "-2.5", "0", "-0.0", "12", "123456.789"):
            with self.subTest(good=good):
                self.assertTrue(IMPL["is_temperature"](good))
        for bad in ("", "nan", "NaN", "1e3", "1,5", "10.4c", " 10.4", "+10.4"):
            with self.subTest(bad=bad):
                self.assertFalse(IMPL["is_temperature"](bad))

    def test_reading_rendering_is_half_away_from_zero(self):
        # AMB-003 / DIFF-001.
        cases = {
            "1.25": "1.3",
            "-1.25": "-1.3",
            "0.05": "0.1",
            "-0.05": "-0.1",
            "0.04": "0.0",
            "-0.04": "0.0",
            "10.44": "10.4",
            "10.45": "10.5",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(IMPL["render_reading"](Fraction(raw)), want)

    def test_mean_rendering_is_half_away_from_zero(self):
        # AMB-003: the mean uses the same rule as the readings.
        self.assertEqual(IMPL["render_mean"](Fraction(21, 10), 2), "1.1")   # 1.05
        self.assertEqual(IMPL["render_mean"](Fraction(-3, 10), 2), "-0.2")  # -0.15
        self.assertEqual(IMPL["render_mean"](Fraction(-1, 10), 2), "-0.1")  # -0.05

    def test_aggregate_consumes_a_header_and_maps_columns_by_name(self):
        # REQ-002: the declared header is consumed and never a reading, and the
        # columns are located by name so a reordered header is still read.
        path = write_temp_csv(
            "station,temperature_c,date\n"
            "ALPHA,1.0,2024-01-01\n"
            "ALPHA,3.0,2024-01-02\n"
        )
        try:
            rows, skipped, total = IMPL["aggregate"](path)
        finally:
            os.unlink(path)
        self.assertEqual(rows, [("ALPHA", 2, "1.0", "3.0", "2.0")])
        self.assertEqual((skipped, total), (0, 2))

    def test_aggregate_reads_a_header_less_document_positionally(self):
        # The declared sample carries no header; a first row that is not the
        # header is a reading (REQ-002).
        path = write_temp_csv("2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,2.0\n")
        try:
            rows, skipped, total = IMPL["aggregate"](path)
        finally:
            os.unlink(path)
        self.assertEqual(rows, [("ALPHA", 2, "1.0", "2.0", "1.5")])
        self.assertEqual((skipped, total), (0, 2))

    def test_aggregate_skips_every_malformed_row_class(self):
        # REQ-005 / AMB-001: wrong field count, empty station, unparseable date
        # and non-numeric temperature are each skipped and excluded.
        path = write_temp_csv(
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "2024-01-01,,2.0\n"
            + "nope,ALPHA,3.0\n"
            + "2024-01-01,ALPHA,NaN\n"
            + "2024-01-01,ALPHA,4.0,extra\n"
            + "\n"
        )
        try:
            rows, skipped, total = IMPL["aggregate"](path)
        finally:
            os.unlink(path)
        self.assertEqual(rows, [("ALPHA", 1, "1.0", "1.0", "1.0")])
        self.assertEqual((skipped, total), (6, 1))

    def test_aggregate_merges_repeated_date_station_keys(self):
        # AMB-002 / REL-003: each occurrence is its own reading.
        path = write_temp_csv(
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA,2.0\n"
            + "2024-01-01,ALPHA,3.0\n"
        )
        try:
            rows, skipped, total = IMPL["aggregate"](path)
        finally:
            os.unlink(path)
        self.assertEqual(rows, [("ALPHA", 3, "1.0", "3.0", "2.0")])
        self.assertEqual((skipped, total), (0, 3))

    def test_aggregate_orders_stations_byte_wise(self):
        # AMB-004 / REQ-007.
        path = write_temp_csv(
            HEADER
            + "2024-01-01,10,1.0\n"
            + "2024-01-01,2,2.0\n"
            + "2024-01-01,B,3.0\n"
            + "2024-01-01,Z,4.0\n"
            + "2024-01-01,a,5.0\n"
        )
        try:
            rows, _, _ = IMPL["aggregate"](path)
        finally:
            os.unlink(path)
        self.assertEqual([row[0] for row in rows], ["10", "2", "B", "Z", "a"])


class EntryPointIntegrationTests(unittest.TestCase):
    """REQ-001: the declared entry point and its first positional argument."""

    def test_the_script_exists_at_the_repository_root(self):
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)

    def test_the_script_is_run_with_bash_and_the_input_path_as_first_argument(self):
        result = subprocess.run(
            ["bash", SCRIPT, "/dev/null"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "SKIPPED 0\nTOTAL 0\n")

    def test_a_readable_input_exits_zero(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)

    def test_the_path_is_taken_from_the_first_argument_not_an_ambient_file(self):
        result = run_csv("2024-01-01,ALPHA,7.5\n")
        self.assertEqual(result.stdout, "ALPHA 1 7.5 7.5 7.5\nSKIPPED 0\nTOTAL 1\n")

    def test_a_missing_input_file_fails_loudly(self):
        missing = os.path.join(tempfile.gettempdir(), "takumi-does-not-exist.csv")
        result = subprocess.run(
            ["bash", SCRIPT, missing],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read", result.stderr)


class ParsingIntegrationTests(unittest.TestCase):
    """REQ-002: the daily temperature CSV is parsed as declared."""

    def test_the_header_is_consumed_and_never_a_reading(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,10.4\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 10.4 10.4 10.4\nSKIPPED 0\nTOTAL 1\n")
        self.assertNotIn("date", result.stdout)

    def test_each_well_formed_row_is_exactly_one_reading(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
            + "2024-01-04,BRAVO,4.0\n"
            + "2024-01-05,BRAVO,5.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(station_lines(result.stdout), [
            "ALPHA 2 1.0 2.0 1.5",
            "BRAVO 3 3.0 5.0 4.0",
        ])
        self.assertEqual(total_of(result.stdout), 5)
        self.assertEqual(skipped_of(result.stdout), 0)

    def test_the_declared_header_less_sample_is_read_positionally(self):
        sample = "2024-01-01,ALPHA,10.4\n2024-01-01,BRAVO,-2.5\n"
        result = run_csv(sample)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 1 10.4 10.4 10.4\nBRAVO 1 -2.5 -2.5 -2.5\nSKIPPED 0\nTOTAL 2\n",
        )

    def test_an_integer_temperature_is_a_valid_numeric_reading(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,12\n")
        self.assertEqual(result.stdout, "ALPHA 1 12.0 12.0 12.0\nSKIPPED 0\nTOTAL 1\n")


class AggregateIntegrationTests(unittest.TestCase):
    """REQ-003 and REQ-004: the printed aggregate lines."""

    def test_one_line_per_station_with_the_exact_aggregates(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-03,ALPHA,9.5\n"
            + "2024-01-01,BRAVO,-2.5\n"
            + "2024-01-02,BRAVO,-1.5\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(station_lines(result.stdout), [
            "ALPHA 3 9.5 11.6 10.5",
            "BRAVO 2 -2.5 -1.5 -2.0",
        ])

    def test_every_station_line_matches_the_declared_shape(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-01,BRAVO,-2.5\n"
        )
        result = run_csv(text)
        lines = station_lines(result.stdout)
        self.assertEqual(len(lines), 2)
        for line in lines:
            with self.subTest(line=line):
                self.assertRegex(line, STATION_SHAPE)
                # Single spaces: splitting on one space and rejoining is exact.
                self.assertEqual(" ".join(line.split(" ")), line)
                self.assertEqual(line.count(" "), 4)

    def test_count_min_max_and_mean_are_recomputed_independently(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.5\n"
            + "2024-01-03,ALPHA,-0.5\n"
            + "2024-01-04,ALPHA,4.0\n"
        )
        result = run_csv(text)
        values = [Fraction("1.0"), Fraction("2.5"), Fraction("-0.5"), Fraction("4.0")]
        expected = "ALPHA %d %s %s %s" % (
            len(values),
            round_half_up_one(min(values)),
            round_half_up_one(max(values)),
            round_half_up_one(sum(values) / len(values)),
        )
        self.assertEqual(station_lines(result.stdout), [expected])

    def test_exactly_one_total_line_equal_to_the_sum_of_the_station_counts(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        result = run_csv(text)
        totals = [line for line in result.stdout.splitlines() if line.startswith("TOTAL ")]
        self.assertEqual(len(totals), 1)
        self.assertEqual(total_of(result.stdout), 3)
        self.assertEqual(total_of(result.stdout), counts_sum(result.stdout))

    def test_a_station_with_no_valid_reading_has_no_line(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "nope,BRAVO,2.0\n"
            + "2024-01-01,,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(station_lines(result.stdout), ["ALPHA 1 1.0 1.0 1.0"])
        self.assertEqual(total_of(result.stdout), 1)
        self.assertEqual(skipped_of(result.stdout), 2)


class MalformedIntegrationTests(unittest.TestCase):
    """REQ-005 / AMB-001 / REL-004: malformed rows never abort the run."""

    def test_every_malformed_class_is_skipped_and_counted(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"          # valid
            + "2024-01-01,ALPHA\n"              # too few fields
            + "2024-01-01,ALPHA,1.0,2.0\n"      # too many fields
            + "2024-01-01,,2.0\n"               # empty station
            + "not-a-date,ALPHA,3.0\n"          # unparseable date
            + "2024-02-30,ALPHA,3.0\n"          # calendar-invalid date
            + "2024-01-01,ALPHA,NaN\n"          # non-numeric temperature
            + "\n"                              # blank line
            + "2024-01-02,BRAVO,4.0\n"          # valid
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(station_lines(result.stdout), [
            "ALPHA 1 1.0 1.0 1.0",
            "BRAVO 1 4.0 4.0 4.0",
        ])
        self.assertEqual(skipped_of(result.stdout), 7)
        self.assertEqual(total_of(result.stdout), 2)

    def test_malformed_rows_never_change_a_count_min_max_or_mean(self):
        clean = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,5.0\n"
        dirty = (
            clean
            + "2024-01-01,ALPHA\n"
            + "2024-01-01,,99.0\n"
            + "bad,ALPHA,-99.0\n"
            + "2024-01-01,ALPHA,not-a-number\n"
        )
        clean_result = run_csv(clean)
        dirty_result = run_csv(dirty)
        self.assertEqual(dirty_result.returncode, 0)
        self.assertEqual(station_lines(dirty_result.stdout), station_lines(clean_result.stdout))
        self.assertEqual(total_of(dirty_result.stdout), total_of(clean_result.stdout))
        self.assertEqual(skipped_of(dirty_result.stdout), 4)

    def test_the_default_decision_is_skip_count(self):
        # AMB-001: a SKIPPED line with the real count, not silent and not fatal.
        result = run_csv(HEADER + "2024-01-01,ALPHA\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIPPED 1\n", result.stdout)
        self.assertIn("TOTAL 0\n", result.stdout)


class OrderingIntegrationTests(unittest.TestCase):
    """REQ-006, REQ-007, REL-001 and AMB-004: determinism and ordering."""

    def test_station_lines_are_ascending_byte_wise(self):
        text = (
            HEADER
            + "2024-01-01,zeta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,alpha,3.0\n"
            + "2024-01-04,10,4.0\n"
            + "2024-01-05,2,5.0\n"
        )
        result = run_csv(text)
        # Byte-wise: '1' < '2' < 'A' < 'Z' < 'a' (ASCII).
        self.assertEqual(
            names_in_order(result.stdout),
            ["10", "2", "ALPHA", "alpha", "zeta", "SKIPPED", "TOTAL"],
        )

    def test_permuting_the_rows_yields_byte_identical_output(self):
        rows = [
            "2024-01-01,ALPHA,1.0",
            "2024-01-01,BRAVO,-3.5",
            "2024-01-02,ALPHA,2.0",
            "2024-01-02,BRAVO,4.5",
            "2024-01-03,CHARLIE,0.0",
            "2024-01-03,ALPHA,2.5",
        ]
        baseline = run_csv(HEADER + "\n".join(rows) + "\n")
        self.assertEqual(baseline.returncode, 0)
        for seed in range(10):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            result = run_csv(HEADER + "\n".join(shuffled) + "\n")
            with self.subTest(seed=seed):
                self.assertEqual(result.stdout, baseline.stdout)

    def test_permuting_malformed_rows_does_not_change_the_skipped_line(self):
        rows = [
            "2024-01-01,ALPHA,1.0",
            "2024-01-01,ALPHA",
            "nope,ALPHA,2.0",
            "2024-01-01,,3.0",
        ]
        baseline = run_csv(HEADER + "\n".join(rows) + "\n")
        for seed in range(5):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            result = run_csv(HEADER + "\n".join(shuffled) + "\n")
            with self.subTest(seed=seed):
                self.assertEqual(result.stdout, baseline.stdout)


class AmbiguityDecisionTests(unittest.TestCase):
    """One test per AMB-nnn entry plus the relations it decides."""

    def test_amb_002_merge_repeated_date_station_keys(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,20.0\n"
            + "2024-01-01,ALPHA,30.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 3 10.0 30.0 20.0\nSKIPPED 0\nTOTAL 3\n")

    def test_amb_003_half_away_from_zero_for_readings(self):
        for raw, want in (("1.25", "1.3"), ("-1.25", "-1.3"), ("0.05", "0.1"), ("-0.05", "-0.1")):
            with self.subTest(raw=raw):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                self.assertEqual(
                    result.stdout,
                    "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want),
                )

    def test_amb_003_half_away_from_zero_for_the_mean(self):
        # -0.1 and -0.2 have mean -0.15, which rounds away from zero to -0.2.
        result = run_csv(HEADER + "2024-01-01,ALPHA,-0.1\n2024-01-02,ALPHA,-0.2\n")
        self.assertIn("ALPHA 2 -0.2 -0.1 -0.2\n", result.stdout)
        # 1.0 and 1.1 have mean 1.05, which rounds away from zero to 1.1.
        positive = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,1.1\n")
        self.assertIn("ALPHA 2 1.0 1.1 1.1\n", positive.stdout)

    def test_amb_005_total_counts_valid_readings_only(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
            + "nope,BRAVO,4.0\n"
            + "2024-01-01,,5.0\n"
        )
        result = run_csv(text)
        self.assertEqual(total_of(result.stdout), 3)
        self.assertEqual(total_of(result.stdout), counts_sum(result.stdout))
        self.assertEqual(skipped_of(result.stdout), 2)

    def test_rel_003_duplicate_rows_all_contribute(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-01,ALPHA,2.0\n"
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 2 1.0 2.0 1.5\nSKIPPED 0\nTOTAL 2\n")

    def test_diff_001_an_independent_aggregation_agrees(self):
        # DIFF-001: recompute count, min, max and mean from the same readings
        # with Fraction arithmetic and half-away-from-zero rounding, and require
        # the tool to print exactly those values.  Several deterministic
        # fixtures, including duplicates and a malformed row, are used.
        def tenths_text(tenths):
            sign = "-" if tenths < 0 else ""
            magnitude = abs(tenths)
            return "%s%d.%d" % (sign, magnitude // 10, magnitude % 10)

        rng = random.Random(20261012)
        for case in range(8):
            rows = []
            truth = {}
            for index in range(rng.randint(5, 40)):
                station = rng.choice(["ALPHA", "BRAVO", "CHARLIE"])
                tenths = rng.randint(-300, 400)
                rows.append(
                    "2024-%02d-%02d,%s,%s"
                    % (index % 12 + 1, index % 28 + 1, station, tenths_text(tenths))
                )
                truth.setdefault(station, []).append(Fraction(tenths, 10))
            if case % 2:
                rows.append("not-a-date,ALPHA,1.0")  # malformed, must not count
            text = HEADER + "\n".join(rows) + "\n"
            result = run_csv(text)
            self.assertEqual(result.returncode, 0)
            expected = []
            for station in sorted(truth, key=lambda name: name.encode("utf-8")):
                values = truth[station]
                expected.append(
                    "%s %d %s %s %s"
                    % (
                        station,
                        len(values),
                        round_half_up_one(min(values)),
                        round_half_up_one(max(values)),
                        round_half_up_one(sum(values) / len(values)),
                    )
                )
            self.assertEqual(station_lines(result.stdout), expected)
            self.assertEqual(result.stdout, reference_output(text))

    def test_rel_002_additivity_holds_with_malformed_rows_present(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
            + "broken,BRAVO,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))
        self.assertEqual(total_of(result.stdout), 3)


class OfflineIntegrationTests(unittest.TestCase):
    """REQ-008: the tool runs without network access."""

    def test_the_source_imports_no_network_module(self):
        with open(SCRIPT, encoding="utf-8") as handle:
            source = handle.read()
        for module in ("socket", "urllib", "http.client", "httplib", "requests", "ftplib"):
            with self.subTest(module=module):
                self.assertNotRegex(
                    source, r"(?m)^\s*(import|from)\s+%s" % re.escape(module)
                )

    def test_the_proxy_poisoned_run_matches_the_plain_run(self):
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = run_csv(text)
        blocked = dict(os.environ)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            blocked[name] = "http://127.0.0.1:9"
        blocked["NO_PROXY"] = ""
        offline = run_csv(text, env=blocked)
        self.assertEqual(offline.returncode, 0)
        self.assertEqual(offline.stdout, baseline.stdout)

    def test_the_tool_produces_the_same_output_with_the_network_namespace_removed(self):
        # A real network-disabled run: unshare(1) drops the network namespace.
        # The tool must still read its local file and print the same report.
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = run_csv(text)
        path = write_temp_csv(text)
        try:
            result = subprocess.run(
                ["unshare", "-rn", "bash", SCRIPT, path],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            self.skipTest("unshare(1) is not available on this host")
        finally:
            os.unlink(path)
        if result.returncode != 0 and "unshare" in result.stderr.lower():
            self.skipTest("unprivileged network namespaces are not permitted: %s" % result.stderr.strip())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, baseline.stdout)


class PerformanceIntegrationTests(unittest.TestCase):
    """REQ-009: about a year of readings finishes in a couple of seconds."""

    @staticmethod
    def _year_fixture(path, rows=200000):
        stations = ["STATION-%03d" % index for index in range(50)]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(HEADER)
            for index in range(rows):
                handle.write(
                    "2024-%02d-%02d,%s,%.1f\n"
                    % (index % 12 + 1, index % 28 + 1, stations[index % len(stations)], -20 + (index % 600) / 10.0)
                )

    def test_two_hundred_thousand_rows_are_summarised_promptly(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        path = handle.name
        handle.close()
        try:
            self._year_fixture(path)
            started = time.perf_counter()
            result = subprocess.run(
                ["bash", SCRIPT, path],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            elapsed = time.perf_counter() - started
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIPPED 0\n", result.stdout)
        self.assertIn("TOTAL 200000\n", result.stdout)
        self.assertEqual(total_of(result.stdout), counts_sum(result.stdout))
        # "A couple of seconds" on a developer laptop; generous enough for a
        # busy CI runner while still failing an accidentally quadratic tool.
        self.assertLess(elapsed, 30.0, "200k rows took %.2fs" % elapsed)


if __name__ == "__main__":
    unittest.main()
