"""Unit and integration tests for the repaired pipeline and the intake contract.

The previous step of this delivery committed the repaired
``.github/workflows/ci.yml``: ``ci_config`` had regenerated the bare skeleton
(naming another project's ``bash pathfind.sh`` entry point) and dropped the
items the delivered project's own suite pins, so the regenerated pipeline could
not run the delivered tests.  The repair restored, and this module pins:

1. the pipeline-wide least-privilege grant ``permissions: contents: read``;
2. a workflow-wide ``concurrency`` block that cancels a superseded run on the
   same ref;
3. the document's declared world (``deliverable.input_format.sample``, all five
   rows in document order) plus the exact-report ``diff`` against it;
4. the declared mutation gate ``bash mutation.sh`` writing
   ``reports/mutation/survivors.json``;
5. a finite ``timeout-minutes`` bound on every job and a shorter inner
   ``timeout`` on every long-running command;
6. the delivered project's own ``run-tests.sh`` smoke-gate entry point.

The module is layered the way the task asks:

* **unit** -- a small workflow reader extracts jobs, job-level timeouts, the
  top-level ``permissions``/``concurrency`` blocks, ``run: |`` bodies and
  heredocs; it is exercised on a synthetic bare skeleton *and* a repaired one,
  so the validator is proven to fail closed when a repair is dropped.
* **integration** -- the real ``ci.yml`` carries every restored item, its
  deliverable heredocs equal the document sample and the independent reference
  report, and the deliverable job's exact shell steps are replayed locally
  against the real ``summary.sh``.
* **acceptance** -- one test per ``REQ-001``..``REQ-009`` criterion and per
  ``AMB-001``..``AMB-005`` decision, through the ``bash summary.sh <csv>``
  process boundary.  ``REL-001``..``REL-004`` and ``DIFF-001`` are pinned by the
  same tests, and a randomised differential run compares the tool against the
  independent reference over many generated fixtures.

The suite is discovered by ``run-tests.sh`` (the smoke gate) and needs no
network.
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
RUNNER = os.path.join(ROOT, "run-tests.sh")
MUTATION = os.path.join(ROOT, "mutation.sh")

EXPECTED_JOBS = {"tests", "deliverable", "mutation"}


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# --------------------------------------------------------------------------
# A minimal reader for the GitHub workflow file.
# --------------------------------------------------------------------------
def parse_jobs(text):
    """Return ``{job-name: [body-lines]}`` for the ``jobs:`` mapping.

    Bodies keep their original indentation so a caller can tell a job-level key
    (four spaces) from a step-level key (eight spaces or deeper).
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
    """The job-level ``timeout-minutes`` in a job body, or ``None``."""
    for line in body:
        match = re.match(r"^    timeout-minutes:\s*([0-9]+)\s*$", line)
        if match:
            return int(match.group(1))
    return None


def top_level_block(text, key):
    """The non-comment lines of a top-level ``key:`` block, or ``None``."""
    match = re.search(r"(?ms)^%s:\s*\n((?:[ \t]+[^\n]*\n)*)" % re.escape(key), text)
    if match is None:
        return None
    return [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def heredocs(text):
    """Return ``{name: [body-lines]}`` for every ``<<'NAME'`` heredoc."""
    found = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        marker = re.search(r"<<'([A-Za-z0-9_]+)'", lines[index])
        if marker is None:
            index += 1
            continue
        name = marker.group(1)
        body = []
        index += 1
        while index < len(lines):
            if lines[index].strip() == name:
                index += 1
                break
            body.append(lines[index].strip())
            index += 1
        found[name] = body
    return found


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


def declared_report():
    """The exact report the declared header-less sample must produce."""
    return reference_output("\n".join(declared_sample()) + "\n").splitlines()


def repair_gaps(text):
    """The restored items a workflow is missing, as human-readable labels."""
    gaps = []
    if top_level_block(text, "permissions") != ["contents: read"]:
        gaps.append("least-privilege permissions")
    concurrency = top_level_block(text, "concurrency") or []
    if not any("cancel-in-progress" in line for line in concurrency):
        gaps.append("workflow concurrency")

    jobs = parse_jobs(text)
    if set(jobs) != EXPECTED_JOBS:
        gaps.append("the three jobs")
    for name, body in jobs.items():
        if job_timeout_minutes(body) is None:
            gaps.append("timeout-minutes on %s" % name)

    if "run-tests.sh" not in "\n".join(jobs.get("tests", [])):
        gaps.append("tests job runs the delivered suite")
    if "bash mutation.sh" not in "\n".join(jobs.get("mutation", [])):
        gaps.append("mutation gate")

    blocks = heredocs(text)
    if blocks.get("TAKUMI_SAMPLE") != declared_sample():
        gaps.append("declared world")
    if blocks.get("TAKUMI_EXPECTED") != declared_report():
        gaps.append("exact report")
    if "diff -u expected.txt report.txt" not in text:
        gaps.append("exact-report diff")
    if not re.search(r"timeout\s+[0-9]+s", text):
        gaps.append("inner command bounds")
    return gaps


# The bare skeleton ``ci_config`` regenerated, including the wrong entry point.
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
        run: bash pathfind.sh
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
          2024-01-01,BRAVO,-2.5
          2024-01-02,ALPHA,11.6
          2024-01-02,BRAVO,-1.5
          2024-01-03,ALPHA,9.5
          TAKUMI_SAMPLE
          cat > expected.txt <<'TAKUMI_EXPECTED'
          ALPHA 3 9.5 11.6 10.5
          BRAVO 2 -2.5 -1.5 -2.0
          SKIPPED 0
          TOTAL 5
          TAKUMI_EXPECTED
          diff -u expected.txt report.txt
  mutation:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - run: timeout 900s bash mutation.sh
"""


# --------------------------------------------------------------------------
# Unit layer: the workflow reader and the repair validator, in isolation.
# --------------------------------------------------------------------------
class WorkflowValidatorUnitTests(unittest.TestCase):
    def test_the_reader_sees_every_job(self):
        self.assertEqual(set(parse_jobs(REPAIRED_SKELETON)), EXPECTED_JOBS)

    def test_the_reader_reads_job_level_timeouts(self):
        jobs = parse_jobs(REPAIRED_SKELETON)
        self.assertEqual(job_timeout_minutes(jobs["tests"]), 30)
        self.assertEqual(job_timeout_minutes(jobs["deliverable"]), 15)
        self.assertEqual(job_timeout_minutes(jobs["mutation"]), 20)

    def test_a_job_without_a_timeout_reports_none(self):
        self.assertIsNone(job_timeout_minutes(parse_jobs(BARE_SKELETON)["tests"]))

    def test_a_step_level_timeout_is_not_a_job_bound(self):
        body = [
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - name: bounded step",
            "        timeout-minutes: 5",
        ]
        self.assertIsNone(job_timeout_minutes(body))

    def test_the_permissions_reader_fails_closed_when_absent(self):
        self.assertIsNone(top_level_block(BARE_SKELETON, "permissions"))

    def test_the_permissions_reader_reads_the_grant(self):
        self.assertEqual(
            top_level_block(REPAIRED_SKELETON, "permissions"), ["contents: read"]
        )

    def test_the_concurrency_reader_fails_closed_when_absent(self):
        self.assertIsNone(top_level_block(BARE_SKELETON, "concurrency"))

    def test_the_heredoc_reader_recovers_the_declared_world(self):
        blocks = heredocs(REPAIRED_SKELETON)
        self.assertEqual(blocks["TAKUMI_SAMPLE"], declared_sample())
        self.assertEqual(blocks["TAKUMI_EXPECTED"], declared_report())

    def test_the_heredoc_reader_returns_nothing_when_absent(self):
        self.assertEqual(heredocs(BARE_SKELETON), {})

    def test_the_validator_reports_every_dropped_repair_on_the_bare_skeleton(self):
        gaps = repair_gaps(BARE_SKELETON)
        for label in (
            "least-privilege permissions",
            "workflow concurrency",
            "the three jobs",
            "mutation gate",
            "declared world",
            "exact report",
            "exact-report diff",
            "inner command bounds",
        ):
            with self.subTest(label=label):
                self.assertIn(label, gaps)
        self.assertTrue(any(gap.startswith("timeout-minutes on") for gap in gaps))

    def test_the_validator_names_the_wrong_entry_point_on_the_bare_skeleton(self):
        # The regenerated skeleton pointed at another project's script; the
        # repaired one must run this project's suite instead.
        self.assertNotIn("pathfind.sh", REPAIRED_SKELETON)
        self.assertIn("run-tests.sh", REPAIRED_SKELETON)

    def test_the_validator_accepts_a_fully_repaired_skeleton(self):
        self.assertEqual(repair_gaps(REPAIRED_SKELETON), [])


# --------------------------------------------------------------------------
# Integration layer: the real workflow the previous step repaired.
# --------------------------------------------------------------------------
class RepairedPipelineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read_text(CI)
        cls.jobs = parse_jobs(cls.text)

    def test_the_repaired_workflow_has_no_missing_repair(self):
        self.assertEqual(repair_gaps(self.text), [])

    def test_the_workflow_declares_exactly_the_three_jobs(self):
        self.assertEqual(set(self.jobs), EXPECTED_JOBS)

    def test_every_job_is_bounded_by_a_finite_timeout(self):
        for name, body in self.jobs.items():
            with self.subTest(job=name):
                bound = job_timeout_minutes(body)
                self.assertIsNotNone(bound, "%s has no job-level timeout" % name)
                self.assertGreater(bound, 0)

    def test_the_workflow_grants_only_read_access(self):
        self.assertEqual(top_level_block(self.text, "permissions"), ["contents: read"])

    def test_no_permission_anywhere_escalates_to_write(self):
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertIsNone(
                re.match(r"^[A-Za-z-]+:\s*(write|write-all)$", stripped),
                "workflow escalates a permission: %r" % stripped,
            )

    def test_the_workflow_cancels_superseded_runs_on_the_same_ref(self):
        concurrency = top_level_block(self.text, "concurrency")
        self.assertIsNotNone(concurrency)
        joined = "\n".join(concurrency)
        self.assertIn("${{ github.workflow }}", joined)
        self.assertIn("${{ github.ref }}", joined)
        self.assertIn("cancel-in-progress: true", joined)

    def test_the_tests_job_runs_the_projects_own_entry_point(self):
        body = "\n".join(self.jobs["tests"])
        self.assertIn("bash run-tests.sh", body)
        self.assertIn("else echo", body)  # fails closed when no entry point is found

    def test_the_deliverable_job_runs_the_declared_command(self):
        body = "\n".join(self.jobs["deliverable"])
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
        self.assertRegex(body, r"timeout\s+[0-9]+s")

    def test_the_workflow_does_not_reference_another_projects_entry_point(self):
        self.assertNotIn("pathfind.sh", self.text)

    def test_the_pipeline_sample_is_the_document_sample_in_order(self):
        self.assertEqual(heredocs(self.text)["TAKUMI_SAMPLE"], declared_sample())

    def test_the_pinned_expectation_is_the_independent_recomputation(self):
        self.assertEqual(heredocs(self.text)["TAKUMI_EXPECTED"], declared_report())


class DeliverableReplayIntegrationTests(unittest.TestCase):
    """Replay the deliverable job's exact shell steps against the real tool."""

    def test_running_the_declared_world_locally_diffs_clean(self):
        sample = "\n".join(declared_sample()) + "\n"
        result = run_csv(sample)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = "\n".join(declared_report()) + "\n"
        self.assertEqual(result.stdout, expected)

        with tempfile.TemporaryDirectory() as directory:
            expected_path = os.path.join(directory, "expected.txt")
            report_path = os.path.join(directory, "report.txt")
            for path, text in ((expected_path, expected), (report_path, result.stdout)):
                with open(path, "w", encoding="utf-8", newline="") as handle:
                    handle.write(text)
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


# --------------------------------------------------------------------------
# Acceptance layer: REQ-001..REQ-009 through the process boundary.
# --------------------------------------------------------------------------
class RequirementAcceptanceTests(unittest.TestCase):
    def test_req_001_the_entry_point_is_a_root_script_run_with_bash_and_dollar_one(self):
        self.assertTrue(os.path.isfile(SCRIPT), SCRIPT)
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")

    def test_req_001_no_argument_is_refused(self):
        result = subprocess.run(
            ["bash", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=60
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage", result.stderr.lower())

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
        self.assertIn("ALPHA 2 1.0 2.0 1.5\n", result.stdout)
        self.assertIn("BRAVO 1 3.0 3.0 3.0\n", result.stdout)

    def test_req_002_the_declared_header_less_sample_is_read_positionally(self):
        result = run_csv("\n".join(declared_sample()) + "\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout, reference_output("\n".join(declared_sample()) + "\n")
        )

    def test_req_003_station_line_shape_and_values(self):
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
        for line in station_lines(result.stdout):
            self.assertRegex(
                line,
                r"^\S+ [0-9]+ -?[0-9]+\.[0-9] -?[0-9]+\.[0-9] -?[0-9]+\.[0-9]$",
            )

    def test_req_003_matches_an_independent_aggregation(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,3.3\n"
            + "2024-01-02,ALPHA,-3.3\n"
            + "2024-01-03,ALPHA,0.05\n"
            + "2024-01-04,BRAVO,7.0\n"
        )
        self.assertEqual(run_csv(text).stdout, reference_output(text))

    def test_req_004_exactly_one_total_equal_to_the_station_sum(self):
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
        for seed in range(8):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            result = run_csv(HEADER + "\n".join(shuffled) + "\n")
            with self.subTest(seed=seed):
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
            names_in_order(result.stdout), ["ALPHA", "alpha", "zeta", "SKIPPED", "TOTAL"]
        )

    def test_req_008_the_same_report_with_network_proxies_poisoned(self):
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = run_csv(text)
        blocked = dict(os.environ)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            blocked[name] = "http://127.0.0.1:9"
        blocked["NO_PROXY"] = ""
        offline = run_csv(text, env=blocked)
        self.assertEqual(offline.returncode, 0)
        self.assertEqual(offline.stdout, baseline.stdout)

    def test_req_008_the_source_imports_no_network_module(self):
        source = read_text(SCRIPT)
        for module in ("socket", "urllib", "requests", "http.client", "ftplib"):
            with self.subTest(module=module):
                self.assertNotIn("import %s" % module, source)

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
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TOTAL 200000\n", result.stdout)
        self.assertLess(elapsed, 30.0, "200k rows took %.2fs" % elapsed)


# --------------------------------------------------------------------------
# Acceptance layer: every AMB-nnn decision and its relation/differential.
# --------------------------------------------------------------------------
class AmbiguityDecisionTests(unittest.TestCase):
    def test_amb_001_skip_count_and_rel_004(self):
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

    def test_amb_002_merge_counts_every_occurrence_and_rel_003(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.0\n"
            + "2024-01-01,ALPHA,20.0\n"
            + "2024-01-01,ALPHA,30.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, "ALPHA 3 10.0 30.0 20.0\nSKIPPED 0\nTOTAL 3\n")

    def test_amb_003_half_away_from_zero_for_readings(self):
        for raw, want in (("1.25", "1.3"), ("-1.25", "-1.3"), ("0.05", "0.1")):
            with self.subTest(raw=raw):
                result = run_csv(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                self.assertEqual(
                    result.stdout,
                    "ALPHA 1 %s %s %s\nSKIPPED 0\nTOTAL 1\n" % (want, want, want),
                )

    def test_amb_003_half_away_from_zero_for_the_mean_and_diff_001(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,1.3\n"
            + "2024-01-03,BRAVO,-1.0\n"
            + "2024-01-04,BRAVO,-1.3\n"
        )
        result = run_csv(text)
        self.assertEqual(result.stdout, reference_output(text))
        self.assertIn("ALPHA 2 1.0 1.3 1.2\n", result.stdout)
        self.assertIn("BRAVO 2 -1.3 -1.0 -1.2\n", result.stdout)

    def test_amb_004_station_lines_ascend_byte_wise(self):
        text = (
            HEADER
            + "2024-01-01,beta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,Zulu,3.0\n"
        )
        result = run_csv(text)
        self.assertEqual(
            names_in_order(result.stdout), ["ALPHA", "Zulu", "beta", "SKIPPED", "TOTAL"]
        )

    def test_amb_005_total_counts_valid_readings_only_and_rel_002(self):
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

    def test_rel_001_permuting_malformed_rows_keeps_the_skipped_count(self):
        rows = [
            "2024-01-01,ALPHA,1.0",
            "not-a-date,ALPHA,2.0",
            "2024-01-02,BRAVO,3.0",
            "2024-01-02,BRAVO",
        ]
        baseline = run_csv(HEADER + "\n".join(rows) + "\n")
        for seed in range(8):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            result = run_csv(HEADER + "\n".join(shuffled) + "\n")
            with self.subTest(seed=seed):
                self.assertEqual(result.stdout, baseline.stdout)


class DifferentialFuzzTests(unittest.TestCase):
    """DIFF-001 / AMB-002 / AMB-003: many generated fixtures vs the reference."""

    STATIONS = ("ALPHA", "BRAVO", "CHARLIE", "alpha", "STATION-01")
    GOOD_DATES = ("2024-01-01", "2024-02-29", "1999-12-31", "2024-06-15")
    BAD_DATES = ("2024-13-01", "2024-02-30", "2024-1-1", "not-a-date", "")
    GOOD_TEMPS = ("0", "0.0", "-0.0", "1.25", "-1.25", "10.45", "-10.45", "99.9")
    BAD_TEMPS = ("", "nan", "1e3", "1,5", "10.4c", "+10.4")

    def _random_document(self, rng, count):
        lines = [HEADER.rstrip("\n")]
        for _ in range(count):
            choice = rng.random()
            if choice < 0.75:
                lines.append(
                    "%s,%s,%s"
                    % (rng.choice(self.GOOD_DATES), rng.choice(self.STATIONS), rng.choice(self.GOOD_TEMPS))
                )
            elif choice < 0.85:
                # malformed temperature
                lines.append(
                    "%s,%s,%s"
                    % (rng.choice(self.GOOD_DATES), rng.choice(self.STATIONS), rng.choice(self.BAD_TEMPS))
                )
            elif choice < 0.93:
                # malformed date
                lines.append(
                    "%s,%s,%s"
                    % (rng.choice(self.BAD_DATES), rng.choice(self.STATIONS), rng.choice(self.GOOD_TEMPS))
                )
            else:
                # wrong field count or empty station
                lines.append(
                    rng.choice(
                        (
                            "%s,,%s" % (rng.choice(self.GOOD_DATES), rng.choice(self.GOOD_TEMPS)),
                            "%s,%s" % (rng.choice(self.GOOD_DATES), rng.choice(self.STATIONS)),
                        )
                    )
                )
        return "\n".join(lines) + "\n"

    def test_generated_fixtures_match_the_independent_reference(self):
        rng = random.Random(20261013)
        for case in range(40):
            text = self._random_document(rng, rng.randint(1, 40))
            with self.subTest(case=case):
                result = run_csv(text)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, reference_output(text))
                self.assertEqual(counts_sum(result.stdout), total_of(result.stdout))


# --------------------------------------------------------------------------
# The smoke gate must be able to run this suite.
# --------------------------------------------------------------------------
class SmokeGateEntryPointTests(unittest.TestCase):
    def test_the_runner_is_a_root_script_that_runs_the_suite(self):
        self.assertTrue(os.path.isfile(RUNNER), RUNNER)
        source = read_text(RUNNER)
        self.assertIn("unittest discover", source)
        self.assertIn("tests", source)

    def test_the_runner_discovery_defaults_to_this_module(self):
        # Running discovery over the default tests directory must find and load
        # this module; an unimportable module would fail the whole suite.
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "tests", os.path.basename(__file__))))

    def test_the_mutation_gate_entry_point_exists(self):
        self.assertTrue(os.path.isfile(MUTATION), MUTATION)

    def test_the_pipeline_invokes_the_smoke_gate(self):
        self.assertIn("bash run-tests.sh", read_text(CI))


if __name__ == "__main__":
    unittest.main()
