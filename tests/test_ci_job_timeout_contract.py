"""Unit and integration tests for the previous step's job-timeout repair.

The previous step (commit ``ci: repair the generated pipeline and bound every
job``) rewrote ``.github/workflows/ci.yml`` after the ``ci_config`` step had
regenerated a weaker skeleton, and additionally bounded *every* job with
``timeout-minutes`` so a hung job fails on its own budget instead of occupying a
runner until the platform kills it.

The restored items (least-privilege grant, workflow-wide concurrency, declared
world, exact-report diff and mutation gate) are pinned by
``test_ci_concurrency_contract.py`` and ``test_ci_pipeline_contract.py``.  The
behavioural delta of *this* step -- the per-job time bound -- was pinned by
nothing, so a regenerated skeleton could silently drop it while the delivered
suite stayed green.  This module is the unit and integration layer for that
delta:

* Unit: a small parser is pointed at synthetic workflows to prove it fails
  closed, that a missing or duplicated bound is visible, and that a
  step-level ``timeout-minutes`` is not mistaken for a job-level one.
* Integration: the parser is run against the real workflow, every job is shown
  to carry exactly one finite bound, and each inner shell ``timeout`` is shown
  to be strictly shorter than its job's bound so the graceful failure fires
  first.

As the test step for this delivery, it also re-runs one independent end-to-end
pass over every REQ-nnn acceptance criterion and every AMB-nnn decision in
``docs/requirements/intake.yaml``, through the real process boundary
(``bash summary.sh <csv>``).

The smoke gate reaches this module through ``bash run-tests.sh``, which
discovers ``tests/test_*.py`` and exits non-zero on any failure.
"""

import os
import random
import re
import subprocess
import tempfile
import time
import unittest

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
from fractions import Fraction

CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")

JOBS = ("tests", "deliverable", "mutation")

# The bounds the previous step chose.  The exact values are pinned so a
# regenerated skeleton cannot quietly loosen a job to the platform maximum (or
# drop the key entirely) and still look green.
EXPECTED_TIMEOUTS = {"tests": 30, "deliverable": 15, "mutation": 20}

# A job-level key sits exactly four spaces in (two for the job name, two more
# for the mapping).  A step-level ``timeout-minutes`` would be indented deeper
# under a ``- name:`` step and must not match.
JOB_TIMEOUT_RE = re.compile(r"^ {4}timeout-minutes:\s*(\S.*?)\s*$")
SHELL_TIMEOUT_RE = re.compile(r"\btimeout\s+([0-9]+)s\b")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def workflow_text():
    return read_text(CI)


def job_blocks(text):
    """Map each job name under the top-level ``jobs:`` to its stripped body."""
    blocks = {}
    current = None
    inside_jobs = False
    for line in text.splitlines():
        if line.rstrip() == "jobs:":
            inside_jobs = True
            continue
        if not inside_jobs:
            continue
        if not line.strip():
            if current is not None:
                blocks[current].append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            # Left the jobs mapping entirely.
            current = None
            inside_jobs = False
            continue
        if indent == 2 and line.rstrip().endswith(":") and not line.lstrip().startswith("- "):
            current = line.strip()[:-1]
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append(line)
    return blocks


def job_timeout_values(text):
    """Map job name -> list of its job-level ``timeout-minutes`` raw values.

    A list is returned rather than a single value so a missing bound (empty
    list) or a duplicated one (two entries) is detectable by the caller.
    """
    values = {}
    for job, body in job_blocks(text).items():
        found = []
        for line in body:
            match = JOB_TIMEOUT_RE.match(line)
            if match is not None:
                found.append(match.group(1))
        values[job] = found
    return values


def shell_timeouts(text):
    """Map job name -> list of the ``timeout Ns`` second counts inside it."""
    result = {}
    for job, body in job_blocks(text).items():
        result[job] = [int(value) for value in SHELL_TIMEOUT_RE.findall("\n".join(body))]
    return result


class TimeoutParserUnitTests(unittest.TestCase):
    """Unit tests for the parser, proved on synthetic workflows."""

    SYNTHETIC = """\
name: ci
on: push
jobs:
  alpha:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: run
        run: echo hi
  beta:
    runs-on: ubuntu-latest
    steps:
      - name: run
        run: echo hi
"""

    def test_every_synthetic_job_is_discovered(self):
        self.assertEqual(sorted(job_blocks(self.SYNTHETIC)), ["alpha", "beta"])

    def test_a_declared_bound_is_read(self):
        values = job_timeout_values(self.SYNTHETIC)
        self.assertEqual(values["alpha"], ["5"])

    def test_a_missing_bound_is_visible_as_an_empty_list(self):
        # The gap the previous step closed: a job with no bound must be
        # observable, not silently treated as bounded.
        values = job_timeout_values(self.SYNTHETIC)
        self.assertEqual(values["beta"], [])

    def test_a_step_level_bound_is_not_counted_as_job_level(self):
        text = """\
jobs:
  gamma:
    runs-on: ubuntu-latest
    steps:
      - name: long step
        timeout-minutes: 3
        run: echo hi
"""
        self.assertEqual(job_timeout_values(text)["gamma"], [])

    def test_a_duplicated_bound_is_visible(self):
        text = """\
jobs:
  delta:
    runs-on: ubuntu-latest
    timeout-minutes: 4
    timeout-minutes: 9
    steps:
      - run: echo hi
"""
        self.assertEqual(job_timeout_values(text)["delta"], ["4", "9"])

    def test_the_parser_stops_at_the_next_top_level_key(self):
        text = """\
jobs:
  epsilon:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    steps:
      - run: echo hi
permissions:
  contents: read
"""
        self.assertEqual(job_timeout_values(text), {"epsilon": ["2"]})

    def test_shell_timeouts_are_read_per_job(self):
        text = """\
jobs:
  zeta:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - run: timeout 120s bash summary.sh sample.csv
      - run: timeout 900s bash mutation.sh
"""
        self.assertEqual(shell_timeouts(text)["zeta"], [120, 900])


class WorkflowJobTimeoutTests(unittest.TestCase):
    """Integration: the real workflow bounds every job it declares."""

    def test_the_workflow_is_present(self):
        self.assertTrue(os.path.isfile(CI), CI)

    def test_the_declared_jobs_are_exactly_the_known_three(self):
        self.assertEqual(set(job_blocks(workflow_text())), set(JOBS))

    def test_every_job_declares_exactly_one_bound(self):
        values = job_timeout_values(workflow_text())
        self.assertEqual(set(values), set(JOBS))
        for job in JOBS:
            with self.subTest(job=job):
                self.assertEqual(
                    len(values[job]),
                    1,
                    "job %r must declare exactly one timeout-minutes" % job,
                )

    def test_every_bound_is_a_plain_positive_integer(self):
        for job, raw_values in job_timeout_values(workflow_text()).items():
            with self.subTest(job=job):
                self.assertEqual(len(raw_values), 1)
                raw = raw_values[0]
                self.assertRegex(raw, r"^[0-9]+$")
                self.assertGreater(int(raw), 0)

    def test_every_bound_is_within_the_platform_maximum(self):
        # GitHub Actions caps a job at 360 minutes; a larger number is rejected
        # rather than ignored, so this is a real ceiling.
        for job, raw_values in job_timeout_values(workflow_text()).items():
            with self.subTest(job=job):
                self.assertLessEqual(int(raw_values[0]), 360)

    def test_the_bounds_are_the_values_the_previous_step_chose(self):
        parsed = {job: int(value[0]) for job, value in job_timeout_values(workflow_text()).items()}
        self.assertEqual(parsed, EXPECTED_TIMEOUTS)

    def test_the_bounds_are_not_all_identical(self):
        # A single blanket value would be a copied constant, not a considered
        # budget; the step chose a different bound for each job.
        values = [int(value[0]) for value in job_timeout_values(workflow_text()).values()]
        self.assertEqual(len(set(values)), len(values))

    def test_the_bounds_sit_inside_the_job_they_belong_to(self):
        # A bound after the last step of the wrong job would still parse if the
        # parser were loose; anchor each value to its own job's steps.
        blocks = job_blocks(workflow_text())
        for job in JOBS:
            body = "\n".join(blocks[job])
            with self.subTest(job=job):
                self.assertRegex(body, r"(?m)^ {4}timeout-minutes:\s*[0-9]+\s*$")
                self.assertIn("steps:", body)

    def test_the_documentation_comment_survives(self):
        text = workflow_text()
        self.assertIn("bounded by `timeout-minutes`", text)

    def test_the_previous_repairs_still_survive(self):
        # The bound was added on top of the earlier repairs; it must not have
        # replaced them.  The dedicated modules pin these in depth; this is a
        # local guard that the timeout change did not regress them.
        text = workflow_text()
        self.assertIn("permissions:\n  contents: read", text)
        self.assertLess(text.index("concurrency:"), text.index("jobs:"))
        self.assertIn("diff -u expected.txt report.txt", text)
        self.assertIn("bash mutation.sh", text)


class ShellTimeoutSubordinationTests(unittest.TestCase):
    """Integration: inner shell timeouts fail before their job bound."""

    def test_every_inner_shell_timeout_is_shorter_than_its_job_bound(self):
        bounds = {
            job: int(value[0]) * 60
            for job, value in job_timeout_values(workflow_text()).items()
        }
        inner = shell_timeouts(workflow_text())
        checked = 0
        for job, seconds_list in inner.items():
            for seconds in seconds_list:
                with self.subTest(job=job, seconds=seconds):
                    self.assertLess(
                        seconds,
                        bounds[job],
                        "inner timeout %ss must be shorter than job %s's %ss bound"
                        % (seconds, job, bounds[job]),
                    )
                    checked += 1
        # The workflow is expected to guard both long-running commands.
        self.assertGreaterEqual(checked, 2)

    def test_the_deliverable_command_is_bounded_below_its_job(self):
        blocks = job_blocks(workflow_text())
        deliverable = "\n".join(blocks["deliverable"])
        self.assertIn("timeout 120s", deliverable)
        self.assertLess(120, EXPECTED_TIMEOUTS["deliverable"] * 60)

    def test_the_mutation_command_is_bounded_below_its_job(self):
        blocks = job_blocks(workflow_text())
        mutation = "\n".join(blocks["mutation"])
        self.assertIn("timeout 900s", mutation)
        self.assertLess(900, EXPECTED_TIMEOUTS["mutation"] * 60)


class ConfirmedRequirementAcceptanceTests(unittest.TestCase):
    """One independent, end-to-end test per REQ-nnn acceptance criterion."""

    def test_req_001_entry_point_reads_the_first_positional_argument(self):
        # A file named summary.sh exists at the repository root, is invoked as
        # `bash summary.sh {csv}`, takes the path from $1 and exits 0.
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")

    def test_req_001_no_other_argument_is_required(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,2.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("ALPHA 1 2.0 2.0 2.0\n", result.stdout)

    def test_req_002_the_header_is_consumed_and_each_valid_row_counts_once(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("date ", result.stdout)
        self.assertEqual(
            station_lines(result.stdout),
            ["ALPHA 2 1.0 2.0 1.5", "BRAVO 1 3.0 3.0 3.0"],
        )

    def test_req_003_one_aggregate_line_per_station(self):
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
            station_lines(result.stdout),
            ["ALPHA 3 9.5 11.6 10.5", "BRAVO 2 -2.5 -1.5 -2.0"],
        )
        shape = re.compile(
            r"^\S+ [0-9]+ -?[0-9]+\.[0-9] -?[0-9]+\.[0-9] -?[0-9]+\.[0-9]$"
        )
        for line in station_lines(result.stdout):
            with self.subTest(line=line):
                self.assertRegex(line, shape)

    def test_req_003_min_max_and_mean_carry_exactly_one_decimal(self):
        for line in station_lines(
            run_csv(HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,2.0\n").stdout
        ):
            fields = line.split(" ")
            with self.subTest(line=line):
                for value in fields[2:]:
                    self.assertRegex(value, r"^-?[0-9]+\.[0-9]$")

    def test_req_004_exactly_one_total_equal_to_the_per_station_sum(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,BRAVO,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        result = run_csv(text)
        total_lines = [
            line for line in result.stdout.splitlines() if line.startswith("TOTAL ")
        ]
        self.assertEqual(total_lines, ["TOTAL 3"])
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))

    def test_req_005_malformed_rows_never_abort_and_never_change_an_aggregate(self):
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
        self.assertEqual(station_lines(result.stdout), ["ALPHA 1 1.0 1.0 1.0"])
        self.assertEqual(skipped_of(result.stdout), 4)
        self.assertEqual(total_of(result.stdout), 1)

    def test_req_006_permuting_the_rows_changes_nothing(self):
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

    def test_req_007_station_lines_ascend_byte_wise(self):
        text = (
            HEADER
            + "2024-01-01,zeta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,alpha,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            names_in_order(result.stdout),
            ["ALPHA", "alpha", "zeta", "SKIPPED", "TOTAL"],
        )

    def test_req_008_the_same_report_with_networking_disabled(self):
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = run_csv(text)
        blocked = dict(os.environ)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            blocked[name] = "http://127.0.0.1:9"
        blocked["NO_PROXY"] = ""
        offline = run_csv(text, env=blocked)
        self.assertEqual(offline.returncode, 0)
        self.assertEqual(offline.stdout, baseline.stdout)

    def test_req_009_two_hundred_thousand_rows_finish_promptly(self):
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


class ConfirmedDecisionAcceptanceTests(unittest.TestCase):
    """One independent, end-to-end test per AMB-nnn chosen behaviour."""

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
        self.assertEqual(skipped_of(result.stdout), 2)
        self.assertEqual(total_of(result.stdout), 2)
        self.assertEqual(
            station_lines(result.stdout),
            ["ALPHA 1 1.0 1.0 1.0", "BRAVO 1 3.0 3.0 3.0"],
        )

    def test_amb_002_merge(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,20.0\n"
            + "2024-01-01,ALPHA,30.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 3 10.0 30.0 20.0\nSKIPPED 0\nTOTAL 3\n")

    def test_amb_003_half_up(self):
        for raw, want in (("1.25", "1.3"), ("-1.25", "-1.3"), ("0.05", "0.1"), ("2.35", "2.4")):
            with self.subTest(raw=raw):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                self.assertEqual(
                    result.stdout,
                    "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want),
                )
                self.assertEqual(want, round_half_up_one(Fraction(raw)))
        # A mean of exactly -0.15 rounds away from zero to -0.2.
        mean = run_csv(HEADER + "2024-01-01,ALPHA,-0.1\n2024-01-02,ALPHA,-0.2\n")
        self.assertIn("ALPHA 2 -0.2 -0.1 -0.2\n", mean.stdout)

    def test_amb_004_ascending_station_id(self):
        text = (
            HEADER
            + "2024-01-01,beta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,Zulu,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            names_in_order(result.stdout),
            ["ALPHA", "Zulu", "beta", "SKIPPED", "TOTAL"],
        )

    def test_amb_005_total_counts_valid_readings_only(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
            + "not-a-date,BRAVO,4.0\n"
        )
        result = run_csv(text)
        self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))
        self.assertEqual(total_of(result.stdout), 3)
        self.assertEqual(skipped_of(result.stdout), 1)


class RequirementDocumentTests(unittest.TestCase):
    """The confirmed document still declares every id and sample this covers."""

    def test_every_covered_requirement_and_ambiguity_is_declared(self):
        text = read_text(DOC)
        for identifier in ["REQ-%03d" % index for index in range(1, 10)]:
            with self.subTest(identifier=identifier):
                self.assertIn(identifier, text)
        for identifier in ["AMB-%03d" % index for index in range(1, 6)]:
            with self.subTest(identifier=identifier):
                self.assertIn(identifier, text)

    def test_the_declared_sample_still_aggregates_to_the_reference(self):
        # Re-derive the document's five-row sample independently and compare
        # against the delivered tool, so this layer is anchored to the document.
        sample = [
            "2024-01-01,ALPHA,10.4",
            "2024-01-01,BRAVO,-2.5",
            "2024-01-02,ALPHA,11.6",
            "2024-01-02,BRAVO,-1.5",
            "2024-01-03,ALPHA,9.5",
        ]
        text = "\n".join(sample) + "\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(text))
        self.assertEqual(
            result.stdout,
            "ALPHA 3 9.5 11.6 10.5\n"
            "BRAVO 2 -2.5 -1.5 -2.0\n"
            "SKIPPED 0\n"
            "TOTAL 5\n",
        )

    def test_the_root_entry_point_is_still_declared(self):
        self.assertIn("bash summary.sh {csv}", read_text(DOC))
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)


if __name__ == "__main__":
    unittest.main()
