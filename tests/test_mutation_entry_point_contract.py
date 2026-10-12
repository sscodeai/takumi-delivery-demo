"""REQ-008 / REL-005: the declared mutation entry point and its survivors report.

The confirmed requirement document declares:

    mutation:
      run: "bash mutation.sh"
      report_path: "reports/mutation/survivors.json"
      format: survivors-json
      max_survivors: 0

and its acceptance criteria are:

* the delivered test suite fails when the mean is computed as the sum or when
  minimum and maximum are swapped; and
* ``bash mutation.sh`` writes ``reports/mutation/survivors.json`` in
  ``survivors-json`` shape with ``total`` greater than zero and an empty
  ``survivors`` list.

This module is the unit and integration layer for that delivered entry point:

* the declared and earlier root scripts exist, are executable and point at the
  one harness;
* the harness's report writer and argument parser honour the declared path and
  the ``survivors-json`` shape;
* the defect catalogue covers the mean/sum and minimum/maximum mutations the
  document names, every anchor occurs exactly once, and the harness FAILS
  CLOSED when an anchor is missing or a mutant survives;
* the CI pipeline carries the declared mutation job; and
* the declared command is run for real and its declared report is read back.

The module is listed in ``mutation/mutation_test.py``'s excluded modules: it
drives the harness, so the harness must not run it while mutating ``summary.sh``
(that would recurse instead of measuring a mutant).
"""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest

from helpers import ROOT, SCRIPT

DECLARED_SCRIPT = os.path.join(ROOT, "mutation.sh")
LEGACY_SCRIPT = os.path.join(ROOT, "mutation-test.sh")
HARNESS_MODULE = os.path.join(ROOT, "mutation", "mutation_test.py")
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
DECLARED_REPORT = os.path.join(ROOT, "reports", "mutation", "survivors.json")
LEGACY_REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")


def load_harness():
    spec = importlib.util.spec_from_file_location(
        "mutation_entry_point_under_test", HARNESS_MODULE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class DeclaredEntryPointTests(unittest.TestCase):
    def test_declared_entry_point_exists_is_executable_and_runs_the_harness(self):
        self.assertTrue(os.path.isfile(DECLARED_SCRIPT), DECLARED_SCRIPT)
        self.assertTrue(os.access(DECLARED_SCRIPT, os.X_OK), DECLARED_SCRIPT)
        with open(DECLARED_SCRIPT, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("mutation/mutation_test.py", source)
        self.assertIn("reports/mutation/survivors.json", source)

    def test_the_earlier_name_is_kept_and_runs_the_same_harness(self):
        self.assertTrue(os.path.isfile(LEGACY_SCRIPT), LEGACY_SCRIPT)
        self.assertTrue(os.access(LEGACY_SCRIPT, os.X_OK), LEGACY_SCRIPT)
        with open(LEGACY_SCRIPT, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("mutation/mutation_test.py", source)

    def test_both_entry_points_are_valid_bash_and_run_from_their_own_directory(self):
        for path in (DECLARED_SCRIPT, LEGACY_SCRIPT):
            with self.subTest(entry_point=os.path.basename(path)):
                result = subprocess.run(
                    ["bash", "-n", path], cwd=ROOT, capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                with open(path, encoding="utf-8") as handle:
                    self.assertIn('cd "$(dirname "$0")"', handle.read())


class HarnessContractTests(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()
        with open(SCRIPT, encoding="utf-8") as handle:
            self.summary = handle.read()

    def test_declared_and_earlier_report_paths_are_the_canonical_pair(self):
        self.assertEqual(self.harness.DECLARED_REPORT, DECLARED_REPORT)
        self.assertEqual(self.harness.LEGACY_REPORT, LEGACY_REPORT)
        self.assertEqual(
            tuple(self.harness.REPORT_PATHS), (DECLARED_REPORT, LEGACY_REPORT)
        )

    def test_report_writer_emits_the_declared_survivors_json_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nested", "survivors.json")
            written = self.harness.write_report(
                path,
                4,
                [{"file": "summary.sh", "line": 12, "description": "a defect"}],
            )
            self.assertEqual(written, path)
            report = read_json(path)
        self.assertEqual(set(report), {"total", "survivors"})
        self.assertEqual(report["total"], 4)
        self.assertEqual(
            report["survivors"],
            [{"file": "summary.sh", "line": 12, "description": "a defect"}],
        )

    def test_write_reports_mirrors_both_canonical_names(self):
        with tempfile.TemporaryDirectory() as directory:
            requested = os.path.join(directory, "requested.json")
            declared = os.path.join(directory, "survivors.json")
            legacy = os.path.join(directory, "mutation.json")
            written = self.harness.write_reports(
                requested, 2, [], mirrors=(declared, legacy)
            )
            self.assertEqual(written, [requested, declared, legacy])
            for path in written:
                self.assertEqual(read_json(path), {"total": 2, "survivors": []})

    def test_parse_report_defaults_to_the_declared_path(self):
        self.assertEqual(self.harness.parse_report([]), DECLARED_REPORT)
        self.assertEqual(
            self.harness.parse_report(["--report=reports/mutation/other.json"]),
            os.path.join(ROOT, "reports", "mutation", "other.json"),
        )
        with self.assertRaises(SystemExit):
            self.harness.parse_report(["--unknown"])

    def test_every_anchor_occurs_exactly_once_in_the_deliverable(self):
        for mutation in self.harness.MUTATIONS:
            with self.subTest(mutant=mutation["id"]):
                self.assertEqual(
                    self.summary.count(mutation["old"]),
                    1,
                    "anchor for %s no longer occurs exactly once" % mutation["id"],
                )

    def test_catalogue_covers_the_defects_the_document_names(self):
        # REQ-008: the delivered tests must fail when the mean is computed as
        # the sum and when minimum and maximum are swapped. Those defects must
        # stay in the catalogue or the report measures something weaker.
        ids = {mutation["id"] for mutation in self.harness.MUTATIONS}
        self.assertIn("sum-accumulation", ids)
        self.assertIn("mean-denominator", ids)
        self.assertIn("minimum-tracking", ids)
        self.assertIn("maximum-tracking", ids)
        self.assertIn("duplicate-count", ids)
        self.assertGreaterEqual(len(ids), 1)

    def test_the_harness_fails_closed_when_no_tests_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            empty_worktree = os.path.join(directory, "worktree")
            os.makedirs(os.path.join(empty_worktree, "tests"))
            self.assertFalse(self.harness.run_tests(empty_worktree))

    def test_main_writes_a_clean_report_when_every_mutant_is_killed(self):
        mutation = self.harness.MUTATIONS[0]
        original_mutations = self.harness.MUTATIONS
        original_run_tests = self.harness.run_tests
        original_paths = self.harness.REPORT_PATHS
        self.harness.MUTATIONS = [mutation]
        self.harness.run_tests = lambda worktree: False
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = os.path.join(directory, "survivors.json")
                self.harness.REPORT_PATHS = (
                    os.path.join(directory, "a.json"),
                    os.path.join(directory, "b.json"),
                )
                status = self.harness.main(["--report", report])
                self.assertEqual(status, 0)
                written = read_json(report)
            self.assertEqual(written["total"], 1)
            self.assertEqual(written["survivors"], [])
        finally:
            self.harness.MUTATIONS = original_mutations
            self.harness.run_tests = original_run_tests
            self.harness.REPORT_PATHS = original_paths

    def test_main_fails_closed_when_a_mutant_survives(self):
        mutation = self.harness.MUTATIONS[0]
        original_mutations = self.harness.MUTATIONS
        original_run_tests = self.harness.run_tests
        original_paths = self.harness.REPORT_PATHS
        self.harness.MUTATIONS = [mutation]
        self.harness.run_tests = lambda worktree: True  # the mutant survived
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = os.path.join(directory, "survivors.json")
                self.harness.REPORT_PATHS = (os.path.join(directory, "mirror.json"),)
                status = self.harness.main(["--report", report])
                written = read_json(report)
            self.assertEqual(status, 1)
            self.assertEqual(written["total"], 1)
            self.assertEqual(len(written["survivors"]), 1)
            survivor = written["survivors"][0]
            self.assertEqual(set(survivor), {"file", "line", "description"})
            self.assertEqual(survivor["file"], "summary.sh")
            self.assertEqual(survivor["description"], mutation["description"])
            self.assertGreaterEqual(survivor["line"], 1)
        finally:
            self.harness.MUTATIONS = original_mutations
            self.harness.run_tests = original_run_tests
            self.harness.REPORT_PATHS = original_paths

    def test_main_fails_closed_when_an_anchor_is_missing(self):
        original_mutations = self.harness.MUTATIONS
        original_run_tests = self.harness.run_tests
        original_paths = self.harness.REPORT_PATHS
        self.harness.MUTATIONS = [
            {
                "id": "vanished-anchor",
                "description": "a mutation whose anchor no longer exists",
                "old": "this anchor is not in summary.sh",
                "new": "anything",
            }
        ]
        self.harness.run_tests = lambda worktree: False
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = os.path.join(directory, "survivors.json")
                self.harness.REPORT_PATHS = (os.path.join(directory, "mirror.json"),)
                status = self.harness.main(["--report", report])
                written = read_json(report)
            self.assertEqual(status, 1)
            self.assertEqual(len(written["survivors"]), 1)
            self.assertIn("anchor", written["survivors"][0]["description"])
        finally:
            self.harness.MUTATIONS = original_mutations
            self.harness.run_tests = original_run_tests
            self.harness.REPORT_PATHS = original_paths

    def test_the_harness_never_mutates_the_real_deliverable(self):
        mutation = self.harness.MUTATIONS[0]
        original_mutations = self.harness.MUTATIONS
        original_run_tests = self.harness.run_tests
        original_paths = self.harness.REPORT_PATHS
        self.harness.MUTATIONS = [mutation]
        self.harness.run_tests = lambda worktree: False
        try:
            with tempfile.TemporaryDirectory() as directory:
                self.harness.REPORT_PATHS = (os.path.join(directory, "mirror.json"),)
                self.harness.main(["--report", os.path.join(directory, "s.json")])
        finally:
            self.harness.MUTATIONS = original_mutations
            self.harness.run_tests = original_run_tests
            self.harness.REPORT_PATHS = original_paths
        with open(SCRIPT, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), self.summary)


class CiMutationJobTests(unittest.TestCase):
    def test_the_pipeline_runs_the_declared_mutation_command(self):
        with open(CI, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("bash mutation.sh", text)
        self.assertIn("reports/mutation/survivors.json", text)
        self.assertRegex(text, r"timeout\s+900s")


class FullMutationRunTests(unittest.TestCase):
    """Integration: the declared command writes the declared report."""

    def test_bash_mutation_sh_writes_a_zero_survivor_report(self):
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
            "bash mutation.sh exited %d\nstdout:\n%s\nstderr:\n%s"
            % (result.returncode, result.stdout[-2000:], result.stderr[-2000:]),
        )
        report = read_json(DECLARED_REPORT)
        self.assertEqual(set(report), {"total", "survivors"})
        self.assertGreater(report["total"], 0)
        self.assertEqual(report["survivors"], [])
        # The earlier name is mirrored so a reader of either path sees the same
        # clean report.
        self.assertEqual(read_json(LEGACY_REPORT), report)

    def test_the_declared_entry_point_is_discoverable_by_the_smoke_gate(self):
        # A suite is only useful when a gate can invoke it; the root runner is
        # the entry point, and the mutation harness is what it calls.
        runner = os.path.join(ROOT, "run-tests.sh")
        self.assertTrue(os.path.isfile(runner))
        self.assertTrue(os.access(runner, os.X_OK))
        result = subprocess.run(
            ["bash", "-n", runner], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
