"""The run-tests.sh smoke-gate entry point.

The delivery task requires a discoverable entry point that runs the suite and
exits non-zero on failure.  These tests drive the runner through a process
boundary against a controlled test directory, so the exit-code contract is
proven without recursing into the real suite.

The runner honours TESTS_DIR and TEST_PATTERN; both default to the repository
suite, so the smoke gate still runs everything when no override is set.
"""

import os
import subprocess
import tempfile
import unittest

from helpers import ROOT

RUNNER = os.path.join(ROOT, "run-tests.sh")

FAILING_TEST = """\
import unittest


class PlantedFailure(unittest.TestCase):
    def test_this_failure_must_be_visible(self):
        self.fail("planted failure: the runner must exit non-zero")
"""

PASSING_TEST = """\
import unittest


class PlantedPass(unittest.TestCase):
    def test_this_pass_keeps_the_runner_green(self):
        self.assertTrue(True)
"""


class RunnerContractTests(unittest.TestCase):
    def _run_runner(self, tests_dir):
        env = dict(os.environ)
        env["TESTS_DIR"] = tests_dir
        return subprocess.run(
            ["bash", RUNNER],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )

    def _write(self, directory, name, source):
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)

    def test_runner_exits_zero_when_the_suite_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write(directory, "test_pass.py", PASSING_TEST)
            result = self._run_runner(directory)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runner_exits_nonzero_when_a_test_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write(directory, "test_fail.py", FAILING_TEST)
            result = self._run_runner(directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stderr + result.stdout)

    def test_runner_exits_nonzero_when_nothing_is_discovered(self):
        # An empty discovery is not a pass: the gate has to fail loudly rather
        # than go green because every test file vanished.
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_runner(directory)
        self.assertNotEqual(result.returncode, 0)

    def test_runner_defaults_to_the_repository_suite(self):
        # The static default preserves the smoke gate's original command.
        with open(RUNNER, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn('TESTS_DIR="${TESTS_DIR:-tests}"', source)
        self.assertIn("unittest discover", source)


if __name__ == "__main__":
    unittest.main()
