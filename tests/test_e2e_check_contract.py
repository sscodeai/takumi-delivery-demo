"""Contract tests for the declared end-to-end CLI check.

The confirmed requirement document declares the deliverable's scenario
(SCN-001):

    run:         "bash e2e/check.sh {csv}"
    report:      ctrf
    report_path: "e2e/report.json"

These tests drive the real entry point through a process boundary, assert the
exit status and the report the document names, and prove the check can fail by
running it against a deliberately broken ``summary.sh`` in a throwaway copy.
Nothing here re-implements the check: it reads the CTRF report the check itself
wrote and the process exit status.
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

from helpers import HEADER, ROOT

CHECK = os.path.join(ROOT, "e2e", "check.sh")
REPORT = os.path.join(ROOT, "e2e", "report.json")

# A world with a header, two stations, a duplicate id and three malformed rows:
# the shape the scenario's expectation is about.
WORLD = (
    HEADER
    + "2024-01-01,ALPHA,10.4\n"
    + "2024-01-01,BRAVO,-2.5\n"
    + "2024-01-02,ALPHA,11.6\n"
    + "2024-01-02,BRAVO,-1.5\n"
    + "2024-01-01,ALPHA\n"
    + "2024-01-01,ALPHA,abc\n"
    + "not-a-date,ALPHA,10.4\n"
)

# The declared world without a header: the document's sample carries none, so
# the check must work there too.
HEADERLESS = (
    "2024-01-01,ALPHA,10.4\n"
    "2024-01-01,BRAVO,-2.5\n"
    "2024-01-02,ALPHA,11.6\n"
    "2024-01-02,BRAVO,-1.5\n"
    "2024-01-03,ALPHA,9.5\n"
)


def write_csv(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    handle.write(text)
    handle.close()
    return handle.name


def run_check(csv_path, cwd=None, check=CHECK):
    return subprocess.run(
        ["bash", check, csv_path],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


def read_report(path=REPORT):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class E2ECheckContractTests(unittest.TestCase):
    def setUp(self):
        self.csv = write_csv(WORLD)
        self.addCleanup(os.unlink, self.csv)

    def test_it_exits_zero_on_the_declared_world(self):
        result = run_check(self.csv)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_it_writes_a_readable_ctrf_report_at_the_declared_path(self):
        result = run_check(self.csv)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(REPORT), "%s was not written" % REPORT)
        report = read_report()
        self.assertEqual(report.get("reportFormat"), "CTRF")
        summary = report["results"]["summary"]
        self.assertGreaterEqual(summary["tests"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["passed"], summary["tests"])

    def test_the_report_names_every_run_at_least_once(self):
        run_check(self.csv)
        report = read_report()
        statuses = [test["status"] for test in report["results"]["tests"]]
        self.assertTrue(statuses)
        self.assertTrue(all(status == "passed" for status in statuses), statuses)

    def test_a_header_less_world_is_checked_too(self):
        path = write_csv(HEADERLESS)
        self.addCleanup(os.unlink, path)
        result = run_check(path)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(read_report()["results"]["summary"]["failed"], 0)

    def test_it_runs_from_any_working_directory(self):
        # The scenario command runs from the repository root; the check must not
        # depend on the caller's cwd to find summary.sh or to write the report.
        with tempfile.TemporaryDirectory() as cwd:
            result = run_check(self.csv, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(REPORT))
        self.assertEqual(read_report()["results"]["summary"]["failed"], 0)

    def test_a_missing_input_file_is_a_non_zero_error(self):
        result = run_check(os.path.join(tempfile.gettempdir(), "does-not-exist-9f3a.csv"))
        self.assertNotEqual(result.returncode, 0)

    def test_no_argument_is_a_non_zero_error(self):
        result = subprocess.run(
            ["bash", CHECK],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage", (result.stdout + result.stderr).lower())

    def test_it_fails_when_the_deliverable_is_wrong(self):
        # A throwaway copy carrying a wrong summary.sh: the check must not pass
        # a report it recomputed differently. This is the check's own negative
        # control, independent of the mutation harness.
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "e2e"))
            shutil.copy2(CHECK, os.path.join(root, "e2e", "check.sh"))
            broken = os.path.join(root, "summary.sh")
            with open(broken, "w", encoding="utf-8") as handle:
                handle.write(
                    "#!/usr/bin/env bash\n"
                    "cat <<'BROKEN'\n"
                    "ALPHA 1 10.4 10.4 9.9\n"
                    "SKIPPED 0\n"
                    "TOTAL 1\n"
                    "BROKEN\n"
                )
            os.chmod(broken, os.stat(broken).st_mode | stat.S_IXUSR)
            result = run_check(self.csv, check=os.path.join(root, "e2e", "check.sh"))
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            report = read_report(os.path.join(root, "e2e", "report.json"))
            self.assertGreater(report["results"]["summary"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
