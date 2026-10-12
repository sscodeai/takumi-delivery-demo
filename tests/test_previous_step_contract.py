"""Unit and integration tests for the previous step's delivery changes.

The previous step (``ci: pin the pipeline to the requirement's declared
world``) repaired ``.github/workflows/ci.yml`` so the pipeline again runs the
confirmed document's world, restored the exact-report ``diff`` and the mutation
gate, and added least-privilege ``permissions: contents: read``. It also
corrected ``README.md``, which had claimed the confirmed document itself
requires a mutation harness.

``test_ci_pipeline_contract.py`` already pins the declared sample and the two
restored jobs. This module adds the layer that was still missing:

* unit tests for the previous step's *new* behaviour -- the workflow-wide
  ``contents: read`` grant (and the absence of any job-level write
  escalation) and the corrected README claim; and
* an integration test that executes the workflow's ``deliverable`` job locally
  the way a runner would -- write the declared world, run ``bash summary.sh``,
  and ``diff`` the report against the pinned expectation -- plus an
  independent, self-contained acceptance pass over every REQ-nnn criterion and
  every AMB-nnn decision in ``docs/requirements/intake.yaml``.

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

from helpers import HEADER, ROOT, SCRIPT, run_csv

CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
README = os.path.join(ROOT, "README.md")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def workflow_heredoc(name):
    """Return the stripped body of the ``<<'name'`` heredoc in the workflow."""
    lines = read_text(CI).splitlines()
    for index, line in enumerate(lines):
        if "<<'%s'" % name not in line:
            continue
        collected = []
        for following in lines[index + 1:]:
            if following.strip() == name:
                return collected
            collected.append(following.strip())
    raise AssertionError("workflow declares no %s heredoc" % name)


def station_lines(stdout):
    return [
        line
        for line in stdout.splitlines()
        if line and not line.startswith(("SKIPPED ", "TOTAL "))
    ]


def skipped_of(stdout):
    return int(
        next(line for line in stdout.splitlines() if line.startswith("SKIPPED ")).split(" ")[1]
    )


def total_of(stdout):
    return int(
        next(line for line in stdout.splitlines() if line.startswith("TOTAL ")).split(" ")[1]
    )


def counts_sum(stdout):
    return sum(int(line.split(" ")[1]) for line in station_lines(stdout))


class WorkflowLeastPrivilegeTests(unittest.TestCase):
    """The previous step's new workflow grant is pinned so it cannot be dropped."""

    def setUp(self):
        self.text = read_text(CI)

    def test_the_workflow_declares_a_top_level_permissions_key(self):
        # A workflow-wide default, at column 0, so every job inherits it.
        self.assertRegex(self.text, r"(?m)^permissions:\s*$")

    def test_the_workflow_grants_only_read_access(self):
        block = re.search(r"(?ms)^permissions:\n((?:[ \t]+[^\n]*\n)*)", self.text)
        self.assertIsNotNone(block, "no top-level permissions block")
        grants = [
            line.strip()
            for line in block.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertEqual(grants, ["contents: read"])

    def test_no_permission_anywhere_escalates_to_write(self):
        # Step *names* may contain the word "write" ("write the declared
        # world"); only a permission grant like `contents: write` matters.
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertIsNone(
                re.match(r"^[A-Za-z-]+:\s*(write|write-all)$", stripped),
                "workflow escalates a permission: %r" % stripped,
            )

    def test_every_job_still_declares_an_ubuntu_runner(self):
        self.assertEqual(self.text.count("runs-on: ubuntu-latest"), 3)


class ReadmeHarnessWordingTests(unittest.TestCase):
    """The previous step's README correction stays true."""

    def test_readme_says_the_document_does_not_require_a_mutation_harness(self):
        text = read_text(README)
        self.assertIn("does not ask for a", text)
        self.assertIn("mutation harness", text)
        self.assertIn("extra quality gate", text)

    def test_readme_no_longer_claims_rel_005_req_008_require_the_harness(self):
        self.assertNotIn("REL-005 / REQ-008 require", read_text(README))


class DeliverableJobIntegrationTests(unittest.TestCase):
    """Run the workflow's declared-world job locally, as a runner would."""

    def _run_deliverable(self, rows):
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

    def test_the_declared_world_runs_and_diffs_clean_against_the_pinned_report(self):
        rows = workflow_heredoc("TAKUMI_SAMPLE")
        expected = "\n".join(workflow_heredoc("TAKUMI_EXPECTED")) + "\n"
        result = self._run_deliverable(rows)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)

        # Mirror the pipeline's `diff -u expected.txt report.txt`, so the exact
        # check the previous step restored is exercised, not just string-equal.
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

    def test_the_declared_world_is_order_independent(self):
        # REL-001: the pinned report is only stable if the world is aggregated
        # as a multiset, so the reversed world must diff clean too.
        rows = workflow_heredoc("TAKUMI_SAMPLE")
        forward = self._run_deliverable(rows)
        backward = self._run_deliverable(list(reversed(rows)))
        self.assertEqual(forward.returncode, 0)
        self.assertEqual(backward.returncode, 0)
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
            station_lines(result.stdout),
            ["ALPHA 3 9.5 11.6 10.5", "BRAVO 2 -2.5 -1.5 -2.0"],
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


if __name__ == "__main__":
    unittest.main()
