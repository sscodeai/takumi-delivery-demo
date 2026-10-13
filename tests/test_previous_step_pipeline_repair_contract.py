"""Unit and integration tests for the previous step's pipeline repair.

The previous step (commit ``ci: repair the regenerated pipeline for the
delivered summary suite``) took the bare skeleton that ``ci_config`` had
regenerated and restored everything the delivered project's own suite pins, so
the pipeline could again judge the delivered ``summary.sh``:

1. the pipeline-wide least-privilege grant ``permissions: contents: read``;
2. the workflow-wide ``concurrency`` block that cancels a superseded run on the
   same ref;
3. the exact declared world under ``deliverable.input_format.sample`` -- all
   five rows, in the document's order -- plus the exact-report ``diff`` against
   it, so a wrong count, min, max, mean, SKIPPED or TOTAL line fails the
   pipeline instead of only the local suite;
4. the declared mutation gate ``bash mutation.sh`` writing
   ``reports/mutation/survivors.json``;
5. and, on top of the restored items, a ``timeout-minutes`` bound on every job
   so a hung job fails on its own budget.

The focused CI modules (``test_ci_concurrency_contract``,
``test_ci_pipeline_contract``, ``test_ci_job_timeout_contract``) pin those
behaviours. This module is the unit and integration layer for the *repair as a
whole*: it parses the workflow into jobs, proves the parser fails closed on a
synthetic bare skeleton, checks the real file carries every restored item, and
runs the deliverable on the declared world exactly as the pipeline does.

It also carries an independent acceptance pass over every ``REQ-nnn``
acceptance criterion and every ``AMB-nnn`` decision in
``docs/requirements/intake.yaml`` through the real process boundary
(``bash summary.sh <csv>``), so the repair is judged against the document, not
against a transcription of it.
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
from reference import reference_output

CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def parse_jobs(text):
    """Return ``{job-name: [body-lines]}`` for the ``jobs:`` mapping.

    The body keeps the original indentation so a caller can tell a job-level
    key (four spaces) from a step-level key (eight spaces or more). Only the
    two-space job names under ``jobs:`` start a new body; everything else is
    appended to the current one.
    """
    jobs = {}
    current = None
    in_jobs = False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            current = None
            continue
        if not in_jobs:
            continue
        name = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if name:
            current = name.group(1)
            jobs[current] = []
            continue
        if current is not None:
            jobs[current].append(line)
    return jobs


def job_timeout_minutes(body):
    """The job-level ``timeout-minutes`` in a job body, or ``None``.

    Only the four-space key is a job bound; a step-level ``timeout-minutes``
    (eight spaces or deeper) must not be mistaken for one.
    """
    for line in body:
        match = re.match(r"^    timeout-minutes:\s*([0-9]+)\s*$", line)
        if match:
            return int(match.group(1))
    return None


def top_level_block(text, key):
    """The non-comment lines of a top-level ``key:`` block, or ``None``.

    Returns ``None`` when the key is absent, so a caller can tell "missing"
    from "declared empty". A block nested under a job never matches because the
    regex anchors the key at column zero.
    """
    match = re.search(
        r"(?ms)^%s:\s*\n((?:[ \t]+[^\n]*\n)*)" % re.escape(key), text
    )
    if match is None:
        return None
    return [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def top_level_permissions(text):
    return top_level_block(text, "permissions")


def top_level_concurrency(text):
    return top_level_block(text, "concurrency")


def heredoc(text, name):
    """Return the stripped body lines of the ``<<'name'`` heredoc in ``text``.

    The heredoc lives inside a ``run: |`` block and is indented, so the lines
    are stripped to recover the text the shell actually feeds the deliverable.
    A missing block raises, so a dropped heredoc is visible instead of empty.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "<<'%s'" % name not in line:
            continue
        collected = []
        for following in lines[index + 1:]:
            if following.strip() == name:
                return collected
            collected.append(following.strip())
    raise AssertionError("workflow declares no %s heredoc" % name)


def declared_sample():
    """The data rows under ``deliverable.input_format.sample`` in the document."""
    lines = read_text(DOC).splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "sample: |":
            continue
        indent = len(line) - len(line.lstrip())
        rows = []
        for following in lines[index + 1:]:
            if following.strip() == "":
                continue
            if len(following) - len(following.lstrip()) <= indent:
                break
            rows.append(following[indent + 2:].rstrip())
        return rows
    raise AssertionError("%s declares no input_format.sample" % DOC)


def missing_repairs(text):
    """The restored items a workflow is missing, as human-readable labels.

    This is the validator the previous step's repair is measured against: on
    the bare ``ci_config`` skeleton it reports every dropped item, and on the
    delivered workflow it reports nothing.
    """
    missing = []
    if top_level_permissions(text) != ["contents: read"]:
        missing.append("least-privilege permissions")
    concurrency = top_level_concurrency(text) or []
    if not any("cancel-in-progress" in line for line in concurrency):
        missing.append("workflow concurrency")
    if "TAKUMI_SAMPLE" not in text:
        missing.append("declared sample")
    if "TAKUMI_EXPECTED" not in text or "diff -u expected.txt report.txt" not in text:
        missing.append("exact-report diff")
    if "bash mutation.sh" not in text:
        missing.append("mutation gate")
    jobs = parse_jobs(text)
    if not jobs:
        missing.append("jobs")
    for name, body in jobs.items():
        if job_timeout_minutes(body) is None:
            missing.append("timeout-minutes on %s" % name)
    return missing


# A workflow with none of the repairs: the shape the ``ci_config`` step
# regenerated and the previous step had to repair.
BARE_SKELETON = """\
name: ci
on:
  push:
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: test
        run: bash run-tests.sh
"""

# The same skeleton with every restored item present.
REPAIRED_SKELETON = """\
name: ci
on:
  push:
permissions:
  contents: read
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
jobs:
  tests:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - run: bash run-tests.sh
  deliverable:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - run: |
          cat > takumi-sample.csv <<'TAKUMI_SAMPLE'
          2024-01-01,ALPHA,10.4
          TAKUMI_SAMPLE
          cat > expected.txt <<'TAKUMI_EXPECTED'
          ALPHA 1 10.4 10.4 10.4
          TAKUMI_EXPECTED
          diff -u expected.txt report.txt
  mutation:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - run: bash mutation.sh
"""


class WorkflowParserUnitTests(unittest.TestCase):
    """The parser and validator used on the real workflow, tested in isolation."""

    def test_the_parser_reads_every_job(self):
        jobs = parse_jobs(REPAIRED_SKELETON)
        self.assertEqual(set(jobs), {"tests", "deliverable", "mutation"})

    def test_the_parser_reads_a_job_level_timeout(self):
        jobs = parse_jobs(REPAIRED_SKELETON)
        self.assertEqual(job_timeout_minutes(jobs["tests"]), 30)
        self.assertEqual(job_timeout_minutes(jobs["mutation"]), 20)

    def test_a_job_without_a_timeout_reports_none(self):
        jobs = parse_jobs(BARE_SKELETON)
        self.assertIsNone(job_timeout_minutes(jobs["tests"]))

    def test_a_step_level_timeout_is_not_a_job_bound(self):
        body = [
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - name: bounded step",
            "        timeout-minutes: 5",
        ]
        self.assertIsNone(job_timeout_minutes(body))

    def test_the_permissions_parser_fails_closed_when_absent(self):
        self.assertIsNone(top_level_permissions(BARE_SKELETON))

    def test_the_concurrency_parser_fails_closed_when_absent(self):
        self.assertIsNone(top_level_concurrency(BARE_SKELETON))

    def test_the_heredoc_parser_fails_closed_on_a_missing_block(self):
        with self.assertRaises(AssertionError):
            heredoc(REPAIRED_SKELETON, "TAKUMI_DOES_NOT_EXIST")

    def test_the_validator_reports_every_dropped_repair_on_the_bare_skeleton(self):
        missing = missing_repairs(BARE_SKELETON)
        for label in (
            "least-privilege permissions",
            "workflow concurrency",
            "declared sample",
            "exact-report diff",
            "mutation gate",
            "timeout-minutes on tests",
        ):
            with self.subTest(label=label):
                self.assertIn(label, missing)

    def test_the_validator_accepts_a_fully_repaired_workflow(self):
        self.assertEqual(missing_repairs(REPAIRED_SKELETON), [])


class DeliveredWorkflowIntegrationTests(unittest.TestCase):
    """The real workflow the previous step repaired."""

    @classmethod
    def setUpClass(cls):
        cls.text = read_text(CI)
        cls.jobs = parse_jobs(cls.text)

    def test_the_workflow_declares_exactly_the_three_jobs(self):
        self.assertEqual(set(self.jobs), {"tests", "deliverable", "mutation"})

    def test_the_validator_finds_no_missing_repair(self):
        self.assertEqual(missing_repairs(self.text), [])

    def test_every_job_is_bounded_by_a_finite_timeout(self):
        for name, body in self.jobs.items():
            with self.subTest(job=name):
                bound = job_timeout_minutes(body)
                self.assertIsNotNone(bound, "%s has no job-level timeout" % name)
                self.assertGreater(bound, 0)

    def test_the_workflow_grants_only_read_access(self):
        self.assertEqual(top_level_permissions(self.text), ["contents: read"])

    def test_no_permission_anywhere_escalates_to_write(self):
        # Step *names* may contain the word "write"; only a grant matters.
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertIsNone(
                re.match(r"^[A-Za-z-]+:\s*(write|write-all)$", stripped),
                "workflow escalates a permission: %r" % stripped,
            )

    def test_the_workflow_cancels_superseded_runs_on_the_same_ref(self):
        concurrency = top_level_concurrency(self.text)
        self.assertIsNotNone(concurrency)
        joined = "\n".join(concurrency)
        self.assertIn("${{ github.workflow }}", joined)
        self.assertIn("${{ github.ref }}", joined)
        self.assertIn("cancel-in-progress: true", joined)

    def test_the_concurrency_block_is_workflow_wide(self):
        # A `concurrency:` key nested under a job would only cover that job; the
        # repair restored a workflow-wide one at column zero.
        self.assertRegex(self.text, r"(?m)^concurrency:\s*$")
        self.assertIsNone(
            re.search(r"(?m)^    concurrency:\s*$", self.text),
            "a job-level concurrency block shadows the workflow-wide one",
        )

    def test_the_tests_job_runs_the_projects_own_suite(self):
        body = "\n".join(self.jobs["tests"])
        self.assertIn("run-tests.sh", body)

    def test_the_deliverable_job_writes_and_runs_the_declared_world(self):
        body = "\n".join(self.jobs["deliverable"])
        self.assertIn("TAKUMI_SAMPLE", body)
        self.assertIn("bash summary.sh takumi-sample.csv", body)
        self.assertRegex(body, r"timeout\s+[0-9]+s")

    def test_the_deliverable_job_diffs_the_exact_report(self):
        body = "\n".join(self.jobs["deliverable"])
        self.assertIn("TAKUMI_EXPECTED", body)
        self.assertIn("diff -u expected.txt report.txt", body)

    def test_the_mutation_job_runs_the_declared_gate(self):
        body = "\n".join(self.jobs["mutation"])
        self.assertIn("bash mutation.sh", body)
        self.assertIn("reports/mutation/survivors.json", body)


class DeclaredWorldIntegrationTests(unittest.TestCase):
    """Run the deliverable on the pipeline's declared world, as a runner would."""

    def _declared_text(self):
        return "\n".join(declared_sample()) + "\n"

    def test_the_pipeline_sample_is_the_document_sample(self):
        self.assertEqual(heredoc(read_text(CI), "TAKUMI_SAMPLE"), declared_sample())
        # The document's sample carries no header line.
        self.assertFalse(
            any(row.split(",")[0].strip().lower() == "date" for row in declared_sample())
        )

    def test_the_pinned_expectation_is_the_independent_recomputation(self):
        expected = heredoc(read_text(CI), "TAKUMI_EXPECTED")
        self.assertEqual(expected, reference_output(self._declared_text()).splitlines())

    def test_running_the_declared_world_locally_diffs_clean(self):
        text = self._declared_text()
        result = run_csv(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = "\n".join(heredoc(read_text(CI), "TAKUMI_EXPECTED")) + "\n"
        self.assertEqual(result.stdout, expected)

        with tempfile.TemporaryDirectory() as directory:
            expected_path = os.path.join(directory, "expected.txt")
            report_path = os.path.join(directory, "report.txt")
            for path, body in ((expected_path, expected), (report_path, result.stdout)):
                with open(path, "w", encoding="utf-8", newline="") as handle:
                    handle.write(body)
            diff = subprocess.run(
                ["diff", "-u", expected_path, report_path],
                capture_output=True,
                text=True,
            )
        self.assertEqual(diff.returncode, 0, diff.stdout + diff.stderr)

    def test_reversing_the_declared_world_keeps_the_output_identical(self):
        rows = declared_sample()
        forward = run_csv("\n".join(rows) + "\n")
        backward = run_csv("\n".join(reversed(rows)) + "\n")
        self.assertEqual(forward.returncode, 0)
        self.assertEqual(backward.returncode, 0)
        self.assertEqual(forward.stdout, backward.stdout)


class ConfirmedRequirementAcceptanceTests(unittest.TestCase):
    """One independent test per REQ-nnn acceptance criterion."""

    def test_req_001_entry_point_reads_the_first_positional_argument(self):
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")

    def test_req_002_header_consumed_and_each_valid_row_is_one_reading(self):
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

    def test_req_003_one_station_line_with_count_min_max_mean(self):
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
            result.stdout,
            "ALPHA 3 9.5 11.6 10.5\nBRAVO 2 -2.5 -1.5 -2.0\nSKIPPED 0\nTOTAL 5\n",
        )

    def test_req_004_exactly_one_total_equal_to_the_per_station_sum(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,BRAVO,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        result = run_csv(text)
        total_lines = [line for line in result.stdout.splitlines() if line.startswith("TOTAL ")]
        self.assertEqual(total_lines, ["TOTAL 3"])
        self.assertEqual(total_of(result.stdout), counts_sum(result.stdout))

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
        self.assertEqual(station_lines(result.stdout), ["ALPHA 1 1.0 1.0 1.0"])
        self.assertEqual(skipped_of(result.stdout), 4)
        self.assertEqual(total_of(result.stdout), 1)

    def test_req_006_permuting_rows_does_not_change_any_line(self):
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

    def test_req_008_the_same_report_with_networking_blocked(self):
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
    """One independent test per AMB-nnn decision."""

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
        for raw, want in (("1.25", "1.3"), ("-1.25", "-1.3"), ("0.05", "0.1")):
            with self.subTest(raw=raw):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                self.assertEqual(
                    result.stdout,
                    "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want),
                )

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


if __name__ == "__main__":
    unittest.main()
