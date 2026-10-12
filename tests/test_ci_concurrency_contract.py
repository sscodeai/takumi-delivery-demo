"""Unit and integration tests for the previous step's pipeline repair.

The previous step (``ci: repair the generated pipeline for the declared
world``) rewrote ``.github/workflows/ci.yml`` after the generated skeleton had
drifted. The behavioural delta of that step is a workflow-wide ``concurrency``
block that cancels a superseded run on the same ref, alongside the three things
the step's message records as restored:

1. the least-privilege grant ``permissions: contents: read``;
2. the exact-report ``diff`` against ``deliverable.input_format.sample``;
3. the declared mutation gate (``bash mutation.sh``, zero survivors).

Nothing pinned the new ``concurrency`` behaviour, so a regenerated workflow
could drop it silently while the delivered suite stayed green. This module is
the unit and integration layer for that step: it parses the workflow, pins the
cancellation contract and the three restored items, executes the pipeline's
declared-world job locally, and re-runs one end-to-end acceptance pass over
every REQ-nnn criterion and every AMB-nnn decision in
``docs/requirements/intake.yaml``.

The acceptance criteria are pinned through the real process boundary
(``bash summary.sh <csv>``), not by importing the implementation.
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
    run_csv,
    skipped_of,
    station_lines,
    total_of,
)
from reference import reference_output

CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")

DECLARED_WORLD = [
    "2024-01-01,ALPHA,10.4",
    "2024-01-01,BRAVO,-2.5",
    "2024-01-02,ALPHA,11.6",
    "2024-01-02,BRAVO,-1.5",
    "2024-01-03,ALPHA,9.5",
]
DECLARED_REPORT = [
    "ALPHA 3 9.5 11.6 10.5",
    "BRAVO 2 -2.5 -1.5 -2.0",
    "SKIPPED 0",
    "TOTAL 5",
]


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def workflow_text():
    return read_text(CI)


def workflow_heredoc(name):
    """Return the stripped body of the ``<<'name'`` heredoc in the workflow."""
    lines = workflow_text().splitlines()
    for index, line in enumerate(lines):
        if "<<'%s'" % name not in line:
            continue
        collected = []
        for following in lines[index + 1:]:
            if following.strip() == name:
                return collected
            collected.append(following.strip())
    raise AssertionError("workflow declares no %s heredoc" % name)


def top_level_block(name):
    """Return the stripped entries of the top-level ``name:`` mapping."""
    lines = workflow_text().splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.rstrip() == name + ":":
            start = index
            break
    if start is None:
        raise AssertionError("workflow declares no top-level %s: block" % name)
    collected = []
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            break
        stripped = line.strip()
        if not stripped.startswith("#"):
            collected.append(stripped)
    return collected


def top_level_key_value(name, key):
    prefix = key + ":"
    for entry in top_level_block(name):
        if entry.startswith(prefix):
            return entry[len(prefix):].strip()
    raise AssertionError("no %r key in the %s block" % (key, name))


class WorkflowConcurrencyTests(unittest.TestCase):
    """Unit tests for the previous step's cancellation contract."""

    def test_the_workflow_declares_a_concurrency_block(self):
        lines = workflow_text().splitlines()
        self.assertEqual(
            sum(1 for line in lines if line.rstrip() == "concurrency:"),
            1,
            "exactly one workflow-wide concurrency block is expected",
        )

    def test_the_concurrency_group_is_per_workflow_and_ref(self):
        group = top_level_key_value("concurrency", "group")
        self.assertEqual(group, "${{ github.workflow }}-${{ github.ref }}")
        self.assertIn("github.workflow", group)
        self.assertIn("github.ref", group)

    def test_superseded_runs_are_cancelled(self):
        self.assertEqual(top_level_key_value("concurrency", "cancel-in-progress"), "true")

    def test_the_concurrency_block_only_declares_the_two_known_keys(self):
        keys = [entry.split(":", 1)[0] for entry in top_level_block("concurrency")]
        self.assertEqual(sorted(keys), ["cancel-in-progress", "group"])

    def test_concurrency_is_not_nested_under_a_job(self):
        # A job-level concurrency block would not cancel a superseded run of the
        # whole pipeline, which is the behaviour the previous step added. The
        # only ``concurrency:`` line must sit at column 0.
        for line in workflow_text().splitlines():
            if line.strip() == "concurrency:":
                with self.subTest(line=line):
                    self.assertFalse(line.startswith((" ", "\t")))

    def test_concurrency_precedes_the_jobs_mapping(self):
        lines = [line.rstrip() for line in workflow_text().splitlines()]
        self.assertLess(lines.index("concurrency:"), lines.index("jobs:"))


class WorkflowRegressionTests(unittest.TestCase):
    """The three items the previous step's message records as restored."""

    def test_the_least_privilege_grant_survives(self):
        self.assertEqual(top_level_block("permissions"), ["contents: read"])

    def test_the_exact_report_diff_survives(self):
        text = workflow_text()
        self.assertIn("TAKUMI_EXPECTED", text)
        self.assertIn("diff -u expected.txt report.txt", text)

    def test_the_declared_mutation_gate_survives(self):
        text = workflow_text()
        self.assertRegex(text, r"(?m)^\s{2}mutation:\s*$")
        self.assertIn("bash mutation.sh", text)
        self.assertIn("reports/mutation/survivors.json", text)

    def test_the_three_jobs_survive(self):
        for job in ("tests:", "deliverable:", "mutation:"):
            with self.subTest(job=job):
                self.assertRegex(workflow_text(), r"(?m)^\s{2}%s\s*$" % re.escape(job))


class DeclaredWorldIntegrationTests(unittest.TestCase):
    """Run the pipeline's declared-world job locally, as a runner would."""

    def test_the_workflow_still_carries_the_declared_world(self):
        self.assertEqual(workflow_heredoc("TAKUMI_SAMPLE"), DECLARED_WORLD)
        self.assertEqual(workflow_heredoc("TAKUMI_EXPECTED"), DECLARED_REPORT)

    def _run(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            sample = os.path.join(directory, "takumi-sample.csv")
            with open(sample, "w", encoding="utf-8", newline="") as handle:
                handle.write("\n".join(rows) + "\n")
            return subprocess.run(
                ["bash", SCRIPT, sample],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )

    def test_the_declared_world_diffs_clean_against_the_pinned_report(self):
        result = self._run(workflow_heredoc("TAKUMI_SAMPLE"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), workflow_heredoc("TAKUMI_EXPECTED"))
        self.assertEqual(result.stdout, reference_output("\n".join(DECLARED_WORLD) + "\n"))

    def test_reversing_the_declared_world_keeps_the_report(self):
        forward = self._run(workflow_heredoc("TAKUMI_SAMPLE"))
        backward = self._run(list(reversed(workflow_heredoc("TAKUMI_SAMPLE"))))
        self.assertEqual(forward.returncode, 0, forward.stderr)
        self.assertEqual(backward.returncode, 0, backward.stderr)
        self.assertEqual(forward.stdout, backward.stdout)


class ConfirmedRequirementAcceptanceTests(unittest.TestCase):
    """One independent, end-to-end test per REQ-nnn acceptance criterion."""

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
        self.assertEqual(
            station_lines(result.stdout),
            ["ALPHA 2 1.0 2.0 1.5", "BRAVO 1 3.0 3.0 3.0"],
        )

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
            station_lines(result.stdout),
            ["ALPHA 3 9.5 11.6 10.5", "BRAVO 2 -2.5 -1.5 -2.0"],
        )
        shape = re.compile(
            r"^\S+ [0-9]+ -?[0-9]+\.[0-9] -?[0-9]+\.[0-9] -?[0-9]+\.[0-9]$"
        )
        for line in station_lines(result.stdout):
            with self.subTest(line=line):
                self.assertRegex(line, shape)

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
        names = [line.split(" ")[0] for line in result.stdout.splitlines() if line]
        self.assertEqual(names, ["ALPHA", "alpha", "zeta", "SKIPPED", "TOTAL"])

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
    """One independent, end-to-end test per AMB-nnn decision."""

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

    def test_amb_004_ascending_station_id(self):
        text = (
            HEADER
            + "2024-01-01,beta,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,Zulu,3.0\n"
        )
        result = run_csv(text)
        names = [line.split(" ")[0] for line in result.stdout.splitlines() if line]
        self.assertEqual(names, ["ALPHA", "Zulu", "beta", "SKIPPED", "TOTAL"])

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
    """The confirmed document still declares the ids this module covers."""

    def test_every_covered_requirement_and_ambiguity_is_declared(self):
        text = read_text(DOC)
        for identifier in ["REQ-%03d" % index for index in range(1, 10)]:
            with self.subTest(identifier=identifier):
                self.assertIn(identifier, text)
        for identifier in ["AMB-%03d" % index for index in range(1, 6)]:
            with self.subTest(identifier=identifier):
                self.assertIn(identifier, text)

    def test_the_document_still_declares_the_root_entry_point(self):
        self.assertIn("bash summary.sh", read_text(DOC))
        self.assertIn("summary.sh", [name for name in os.listdir(ROOT)])


if __name__ == "__main__":
    unittest.main()
