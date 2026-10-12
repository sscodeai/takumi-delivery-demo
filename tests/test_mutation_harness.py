"""Self-tests for the mutation harness (REQ-005).

The confirmed requirement document declares the mutation contract:

    mutation:
      run: "bash mutation-test.sh"
      report_path: "reports/mutation/mutation.json"
      format: survivors-json
      max_survivors: 0

These tests pin the parts of that contract that can be checked without paying
for a full mutation run:

* the entry point exists and points at the harness;
* every mutation anchor still occurs exactly once in summary.sh, so the harness
  cannot quietly lose a mutant when the source drifts;
* the harness measures at least one mutant;
* the report writer emits exactly the declared survivors-json shape;
* the harness runs the delivered CLI tests and excludes only the modules that
  exercise the separate HTTP artifact or the harness itself.
"""

import importlib.util
import json
import os
import tempfile
import unittest

from helpers import ROOT, SCRIPT

HARNESS_SCRIPT = os.path.join(ROOT, "mutation-test.sh")
HARNESS_MODULE = os.path.join(ROOT, "mutation", "mutation_test.py")


def load_harness():
    spec = importlib.util.spec_from_file_location("mutation_test_under_test", HARNESS_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MutationContractTests(unittest.TestCase):
    def setUp(self):
        self.harness = load_harness()
        with open(SCRIPT, encoding="utf-8") as handle:
            self.summary = handle.read()

    def test_entry_point_exists_and_runs_the_harness(self):
        self.assertTrue(os.path.isfile(HARNESS_SCRIPT))
        with open(HARNESS_SCRIPT, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("mutation/mutation_test.py", source)

    def test_every_anchor_occurs_exactly_once(self):
        # A drifting anchor is reported as a survivor at run time, but a silent
        # rename here would be a lost mutant; fail the build instead.
        for mutation in self.harness.MUTATIONS:
            self.assertEqual(
                self.summary.count(mutation["old"]),
                1,
                "anchor for %s does not occur exactly once" % mutation["id"],
            )

    def test_the_harness_measures_at_least_one_mutant(self):
        self.assertGreaterEqual(len(self.harness.MUTATIONS), 1)

    def test_mutants_are_distinct(self):
        seen = set()
        for mutation in self.harness.MUTATIONS:
            self.assertNotIn(mutation["id"], seen)
            seen.add(mutation["id"])
            self.assertNotEqual(mutation["old"], mutation["new"])

    def test_report_is_the_declared_survivors_json_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nested", "mutation.json")
            written = self.harness.write_report(
                path,
                3,
                [{"file": "summary.sh", "line": 7, "description": "a defect"}],
            )
            self.assertEqual(written, path)
            with open(path, encoding="utf-8") as handle:
                report = json.load(handle)
        self.assertEqual(set(report), {"total", "survivors"})
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["survivors"], [{"file": "summary.sh", "line": 7, "description": "a defect"}])

    def test_the_cli_suite_excludes_only_non_cli_modules(self):
        tests_dir = os.path.join(ROOT, "tests")
        modules = self.harness.cli_test_modules(tests_dir)
        self.assertIn("test_aggregates", modules)
        self.assertIn("test_malformed", modules)
        self.assertNotIn("test_service", modules)
        self.assertNotIn("test_service_units", modules)
        self.assertNotIn("test_mutation_harness", modules)

    def test_line_of_points_at_the_anchor(self):
        line = self.harness.line_of(self.summary, "if len(row) != 3:")
        self.assertEqual(self.summary.splitlines()[line - 1].strip(), "if len(row) != 3:")


if __name__ == "__main__":
    unittest.main()
