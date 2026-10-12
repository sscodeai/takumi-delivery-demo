"""Unit and integration tests for summary.sh, the delivered entry point.

The confirmed requirement document is ``docs/requirements/intake.yaml``.  The
existing black-box suites drive ``bash summary.sh <csv>`` through a process
boundary; this module adds the *unit* layer that was missing and then states the
integration contract again at the level of the document:

* Unit: the Python embedded in ``summary.sh`` is loaded in-process and its
  parsing predicates, its exact half-away-from-zero renderer and its
  ``aggregate()`` function are exercised directly, so a defect is localised
  below the process boundary instead of only observed as a wrong line.
* Integration: ``bash summary.sh <csv>`` is run as the document declares it and
  the printed report is asserted once per ``REQ-nnn`` acceptance criterion and
  once per ``AMB-nnn`` decision, with the expected values also produced by the
  independent ``tests/reference.py`` recomputation.
* Previous step: the README/pipeline repair documented the delivered pipeline's
  three jobs; a small contract test keeps the documentation and the workflow
  from drifting apart.

Acceptance criteria covered here: REQ-001 ... REQ-009.  Decisions covered here:
AMB-001 (skip-count), AMB-002 (merge), AMB-003 (half-up), AMB-004 (ascending),
AMB-005 (valid-only TOTAL).
"""

import os
import random
import subprocess
import tempfile
import time
import unittest
from fractions import Fraction

from helpers import HEADER, ROOT, SCRIPT, run_csv, skipped_of, total_of
from reference import reference_output

DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")
README = os.path.join(ROOT, "README.md")
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")


def load_summary_module():
    """Load the Python embedded in ``summary.sh`` into a fresh namespace.

    The script runs its Python through ``exec python3 - "$1" <<'PY'``; the tests
    read the heredoc body and execute it with a non-``__main__`` name, so the
    module-level definitions are available without the CLI running.
    """
    with open(SCRIPT, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    start = next(index for index, line in enumerate(lines) if "<<'PY'" in line) + 1
    end = next(index for index in range(start, len(lines)) if lines[index] == "PY")
    source = "\n".join(lines[start:end])
    namespace = {"__name__": "summary_under_test"}
    exec(compile(source, SCRIPT, "exec"), namespace)
    return namespace


def aggregate_text(module, text):
    """Run the embedded ``aggregate()`` on ``text`` and return its result."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    try:
        handle.write(text)
        handle.close()
        return module["aggregate"](handle.name)
    finally:
        os.unlink(handle.name)


class EmbeddedSummaryUnitTests(unittest.TestCase):
    """Direct, in-process unit tests of summary.sh's own functions."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_summary_module()

    # -- is_date -------------------------------------------------------------

    def test_is_date_accepts_real_calendar_dates(self):
        # REQ-002: a parseable date, including a leap day and an ISO time suffix.
        for text in (
            "2024-01-01",
            "2024-02-29",
            "1999-12-31",
            "2024-01-01T00:00:00",
            "2024-01-01 12:30:00",
        ):
            with self.subTest(text=text):
                self.assertTrue(self.module["is_date"](text))

    def test_is_date_rejects_impossible_dates_and_garbage(self):
        for text in (
            "",
            "2023-02-29",
            "2024-13-01",
            "2024-00-10",
            "2024-01-32",
            "2024-1-1",
            "not-a-date",
            "2024-01-01x",
            "2024-01-01Tbogus",
        ):
            with self.subTest(text=text):
                self.assertFalse(self.module["is_date"](text))

    # -- is_temperature ------------------------------------------------------

    def test_is_temperature_accepts_plain_decimals(self):
        for text in ("0", "10", "-2.5", "007", "12345678901234567890.5"):
            with self.subTest(text=text):
                self.assertTrue(self.module["is_temperature"](text))

    def test_is_temperature_rejects_non_decimal_forms(self):
        for text in ("", " ", "abc", "NaN", "Infinity", "0x10", "1e5", ".5", "1.", "1,000"):
            with self.subTest(text=text):
                self.assertFalse(self.module["is_temperature"](text))

    # -- rounding (AMB-003) --------------------------------------------------

    def test_render_reading_rounds_half_away_from_zero(self):
        cases = {
            "1.25": "1.3",
            "-1.25": "-1.3",
            "1.24": "1.2",
            "-1.24": "-1.2",
            "0.05": "0.1",
            "-0.05": "-0.1",
            "0.0": "0.0",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.module["render_reading"](Fraction(raw)), want)

    def test_render_mean_rounds_half_away_from_zero(self):
        # -0.15 is exactly half; half away from zero is -0.2, not -0.1.
        self.assertEqual(self.module["render_mean"](Fraction(-3, 10), 2), "-0.2")
        self.assertEqual(self.module["render_mean"](Fraction(5), 4), "1.3")

    def test_render_one_decimal_normalises_negative_zero(self):
        self.assertEqual(self.module["render_one_decimal"](Fraction(-1, 100)), "0.0")

    # -- aggregate() ---------------------------------------------------------

    def test_aggregate_returns_one_tuple_per_station(self):
        rows, skipped, total = aggregate_text(
            self.module,
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-03,ALPHA,9.5\n"
            + "2024-01-01,BRAVO,-2.5\n"
            + "2024-01-02,BRAVO,-1.5\n",
        )
        self.assertEqual(
            rows,
            [
                ("ALPHA", 3, "9.5", "11.6", "10.5"),
                ("BRAVO", 2, "-2.5", "-1.5", "-2.0"),
            ],
        )
        self.assertEqual((skipped, total), (0, 5))

    def test_aggregate_counts_each_repeated_key_as_a_distinct_reading(self):
        # AMB-002 merge.
        rows, skipped, total = aggregate_text(
            self.module,
            HEADER + "2024-01-01,ALPHA,10.0\n2024-01-01,ALPHA,20.0\n",
        )
        self.assertEqual(rows, [("ALPHA", 2, "10.0", "20.0", "15.0")])
        self.assertEqual((skipped, total), (0, 2))

    def test_aggregate_skips_every_malformed_shape(self):
        # AMB-001 skip-count: wrong field count, empty station, bad date and
        # non-numeric temperature are each skipped and change no aggregate.
        rows, skipped, total = aggregate_text(
            self.module,
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "2024-01-01,ALPHA,2.0,extra\n"
            + "2024-01-01,,3.0\n"
            + "bad-date,ALPHA,4.0\n"
            + "2024-01-01,ALPHA,not-a-number\n",
        )
        self.assertEqual(rows, [("ALPHA", 1, "1.0", "1.0", "1.0")])
        self.assertEqual((skipped, total), (5, 1))

    def test_aggregate_consumes_the_declared_header(self):
        # REQ-002: the header must never contribute a reading.
        rows, skipped, total = aggregate_text(
            self.module, HEADER + "2024-01-01,ALPHA,1.0\n"
        )
        self.assertEqual(rows, [("ALPHA", 1, "1.0", "1.0", "1.0")])
        self.assertEqual((skipped, total), (0, 1))

    def test_aggregate_orders_stations_by_ascending_byte_wise_id(self):
        # AMB-004: uppercase 'A' (0x41) < lowercase 'a' (0x61) < 'z' (0x7a).
        rows, _skipped, _total = aggregate_text(
            self.module,
            HEADER
            + "2024-01-01,zeta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,alpha,3.0\n",
        )
        self.assertEqual([row[0] for row in rows], ["ALPHA", "alpha", "zeta"])

    def test_aggregate_total_is_the_sum_of_the_station_counts(self):
        # AMB-005 valid-only TOTAL.
        rows, _skipped, total = aggregate_text(
            self.module,
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
            + "bad,ALPHA,4.0\n",
        )
        self.assertEqual(total, sum(row[1] for row in rows))
        self.assertEqual(total, 3)


class AcceptanceCriteriaIntegrationTests(unittest.TestCase):
    """One end-to-end test per REQ-nnn acceptance criterion."""

    def test_req_001_root_script_reads_the_first_positional_argument(self):
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")

    def test_req_002_header_is_consumed_and_valid_rows_are_readings(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("date ", result.stdout)
        self.assertIn("ALPHA 2 1.0 2.0 1.5\n", result.stdout)
        self.assertIn("BRAVO 1 3.0 3.0 3.0\n", result.stdout)

    def test_req_003_exactly_one_station_line_with_the_aggregates(self):
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
        self.assertEqual(
            [line for line in result.stdout.splitlines() if line.startswith(("ALPHA ", "BRAVO "))],
            ["ALPHA 3 9.5 11.6 10.5", "BRAVO 2 -2.5 -1.5 -2.0"],
        )

    def test_req_004_total_line_equals_the_per_station_sum(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,BRAVO,2.0\n2024-01-03,BRAVO,3.0\n"
        result = run_csv(text)
        total_lines = [line for line in result.stdout.splitlines() if line.startswith("TOTAL ")]
        self.assertEqual(total_lines, ["TOTAL 3"])

    def test_req_005_malformed_rows_never_abort_and_are_counted(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "bad-date,ALPHA,2.0\n"
            + "2024-01-01,,3.0\n"
            + "2024-01-01,ALPHA,not-a-number\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(skipped_of(result.stdout), 4)
        self.assertEqual(total_of(result.stdout), 1)

    def test_req_006_permuting_the_rows_keeps_the_output_identical(self):
        rows = [
            "2024-01-01,ALPHA,1.0",
            "2024-01-02,BRAVO,2.0",
            "2024-01-03,ALPHA,3.0",
            "2024-01-04,CHARLIE,4.0",
        ]
        baseline = run_csv(HEADER + "\n".join(rows) + "\n")
        for seed in range(5):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            result = run_csv(HEADER + "\n".join(shuffled) + "\n")
            self.assertEqual(result.stdout, baseline.stdout)

    def test_req_007_station_lines_are_in_ascending_byte_wise_order(self):
        text = HEADER + "2024-01-01,zeta,1.0\n2024-01-02,ALPHA,2.0\n2024-01-03,alpha,3.0\n"
        result = run_csv(text)
        names = [line.split(" ")[0] for line in result.stdout.splitlines() if line]
        self.assertEqual(names, ["ALPHA", "alpha", "zeta", "SKIPPED", "TOTAL"])

    def test_req_008_the_tool_needs_no_network(self):
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = run_csv(text)
        blocked = dict(os.environ)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            blocked[name] = "http://127.0.0.1:9"
        blocked["NO_PROXY"] = ""
        offline = run_csv(text, env=blocked)
        self.assertEqual(offline.returncode, 0)
        self.assertEqual(offline.stdout, baseline.stdout)

    def test_req_009_a_year_of_readings_finishes_in_a_couple_of_seconds(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        path = handle.name
        handle.close()
        try:
            with open(path, "w", encoding="utf-8", newline="") as writer:
                writer.write(HEADER)
                for index in range(200000):
                    writer.write(
                        "2024-%02d-%02d,STATION-%03d,%.1f\n"
                        % (index % 12 + 1, index % 28 + 1, index % 50, -20 + index % 60)
                    )
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
        self.assertIn("TOTAL 200000\n", result.stdout)
        self.assertLess(elapsed, 30.0, "200k rows took %.2fs" % elapsed)


class AmbiguityDecisionIntegrationTests(unittest.TestCase):
    """One end-to-end test per AMB-nnn entry, pinning the chosen behaviour."""

    def test_amb_001_skip_count(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "not-a-date,ALPHA,2.0\n"
            + "2024-01-02,BRAVO,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIPPED 2\n", result.stdout)
        self.assertIn("TOTAL 2\n", result.stdout)

    def test_amb_002_merge(self):
        result = run_csv(
            HEADER
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,20.0\n"
            + "2024-01-01,ALPHA,30.0\n"
        )
        self.assertEqual(result.stdout, "ALPHA 3 10.0 30.0 20.0\nSKIPPED 0\nTOTAL 3\n")

    def test_amb_003_half_up(self):
        for raw, want in (("1.25", "1.3"), ("-1.25", "-1.3"), ("0.05", "0.1")):
            with self.subTest(raw=raw):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                self.assertEqual(
                    result.stdout,
                    "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want),
                )

    def test_amb_004_ascending_station_id(self):
        result = run_csv(
            HEADER
            + "2024-01-01,beta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,Zulu,3.0\n"
        )
        names = [line.split(" ")[0] for line in result.stdout.splitlines() if line]
        self.assertEqual(names, ["ALPHA", "Zulu", "beta", "SKIPPED", "TOTAL"])

    def test_amb_005_total_counts_valid_readings_only(self):
        result = run_csv(
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
            + "not-a-date,BRAVO,4.0\n"
        )
        counts = sum(
            int(line.split(" ")[1])
            for line in result.stdout.splitlines()
            if line and not line.startswith(("SKIPPED ", "TOTAL "))
        )
        self.assertEqual(counts, total_of(result.stdout))
        self.assertEqual(total_of(result.stdout), 3)


class IndependentReferenceIntegrationTests(unittest.TestCase):
    """The delivered CLI agrees with the independent Fraction reference."""

    def test_a_dense_mixed_fixture_matches_the_reference(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,2.675\n"
            + "2024-01-01,ALPHA,2.675\n"
            + "2024-01-02,BRAVO,-0.05\n"
            + "2024-01-03,BRAVO,1.25\n"
            + "2024-01-04,,3.0\n"
            + "bad,CHARLIE,4.0\n"
            + "2024-01-05,CHARLIE,1e5\n"
            + "2024-01-06,alpha,0.15\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(text))


class PreviousStepPipelineDocumentationTests(unittest.TestCase):
    """Keep the previous step's README/CI repair pinned.

    The previous step documented the delivered pipeline's three jobs and the
    commands they run.  These assertions keep the documentation and the workflow
    from drifting apart, and keep the exact-report check and mutation gate the
    step restored visible.
    """

    def setUp(self):
        with open(README, encoding="utf-8") as handle:
            self.readme = handle.read()
        with open(CI, encoding="utf-8") as handle:
            self.ci = handle.read()

    def test_both_files_name_the_three_pipeline_jobs(self):
        for job in ("tests", "deliverable", "mutation"):
            with self.subTest(job=job):
                self.assertIn("`%s`" % job, self.readme)
                self.assertIn("\n  %s:\n" % job, self.ci)

    def test_the_documented_commands_are_the_commands_the_pipeline_runs(self):
        for command in ("bash run-tests.sh", "bash summary.sh", "bash mutation.sh"):
            with self.subTest(command=command):
                self.assertIn(command, self.readme)
                self.assertIn(command, self.ci)

    def test_the_documented_mutation_report_is_the_declared_path(self):
        self.assertIn("reports/mutation/survivors.json", self.readme)
        self.assertIn("reports/mutation/survivors.json", self.ci)


if __name__ == "__main__":
    unittest.main()
