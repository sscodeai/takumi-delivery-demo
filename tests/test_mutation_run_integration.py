"""The previous step's declared mutation entry point, pinned end to end.

The implementation this run tests added ``mutation/run.sh`` as the mutation
entry point named by the requirement run:

    mutation:
      run:           bash mutation/run.sh
      report_path:   reports/mutation/mutation.json
      format:        survivors-json   {"total": <int>, "survivors": [...]}
      max_survivors: 0

``test_mutation_run_entrypoint`` pins that script statically.  This module is
its behavioural counterpart: it actually RUNS ``bash mutation/run.sh``, proves
the script forwards to the one harness without a full mutant sweep (``--help``),
and reads the declared ``reports/mutation/mutation.json`` report back with a
positive mutant total and an empty survivors list.

The full run drives the harness, which runs the delivered CLI suite inside a
throwaway copy of the project, so this module is listed in
``mutation/mutation_test.py``'s ``EXCLUDED_MODULES``: the harness must not run
it while mutating ``summary.sh`` or it would recurse instead of measuring a
mutant.  ``test_mutation_harness`` pins that exclusion.
"""

import json
import os
import stat
import subprocess
import unittest

from helpers import ROOT

DECLARED_SCRIPT = os.path.join(ROOT, "mutation", "run.sh")
HARNESS = os.path.join(ROOT, "mutation", "mutation_test.py")
# The run's declared report path; the harness also mirrors it to the earlier
# name, reports/mutation/survivors.json, so a reader of either sees one report.
DECLARED_REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")
MIRROR_REPORT = os.path.join(ROOT, "reports", "mutation", "survivors.json")
RUNNER = os.path.join(ROOT, "run-tests.sh")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class DeclaredMutationRunStaticTests(unittest.TestCase):
    def test_the_declared_entry_point_exists_and_is_executable(self):
        self.assertTrue(os.path.isfile(DECLARED_SCRIPT), DECLARED_SCRIPT)
        mode = os.stat(DECLARED_SCRIPT).st_mode
        self.assertTrue(mode & stat.S_IXUSR, "mutation/run.sh is not executable")

    def test_the_declared_entry_point_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", DECLARED_SCRIPT], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_declared_entry_point_runs_from_the_repository_root(self):
        # mutation/run.sh lives one directory below the root, so it must climb
        # back up before invoking the harness; otherwise the declared report
        # path would resolve relative to mutation/.
        self.assertIn('cd "$(dirname "$0")/.."', read_text(DECLARED_SCRIPT))

    def test_the_declared_entry_point_runs_the_harness_at_the_declared_path(self):
        source = read_text(DECLARED_SCRIPT)
        self.assertIn("mutation/mutation_test.py", source)
        self.assertIn("reports/mutation/mutation.json", source)
        self.assertTrue(os.path.isfile(HARNESS), HARNESS)

    def test_the_declared_entry_point_forwards_extra_arguments(self):
        # `"$@"` is what lets a caller override the report (the harness parses
        # `--report PATH`); dropping it would silently ignore the caller.
        self.assertIn('"$@"', read_text(DECLARED_SCRIPT))

    def test_the_smoke_gate_entry_point_is_discoverable(self):
        # The step's own contract: the host has to be able to run the suite.
        self.assertTrue(os.path.isfile(RUNNER), RUNNER)
        self.assertTrue(os.access(RUNNER, os.X_OK), RUNNER)
        result = subprocess.run(
            ["bash", "-n", RUNNER], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class DeclaredMutationRunForwardingTests(unittest.TestCase):
    """A cheap process-boundary run that proves the script reaches the harness."""

    def test_help_reaches_the_harness_and_exits_zero(self):
        result = subprocess.run(
            ["bash", DECLARED_SCRIPT, "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("usage: mutation_test.py", result.stdout + result.stderr)


class DeclaredMutationRunIntegrationTests(unittest.TestCase):
    """Run the declared command for real and read its declared report back."""

    def test_the_declared_command_writes_the_declared_report(self):
        result = subprocess.run(
            ["bash", DECLARED_SCRIPT],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )
        self.assertEqual(
            result.returncode,
            0,
            "bash mutation/run.sh exited %d\nstdout:\n%s\nstderr:\n%s"
            % (result.returncode, result.stdout[-2000:], result.stderr[-2000:]),
        )
        report = read_json(DECLARED_REPORT)
        self.assertEqual(set(report), {"total", "survivors"})
        self.assertGreater(report["total"], 0)
        self.assertEqual(report["survivors"], [])
        # The earlier name is mirrored so both recorded report paths agree.
        self.assertEqual(read_json(MIRROR_REPORT), report)


if __name__ == "__main__":
    unittest.main()
