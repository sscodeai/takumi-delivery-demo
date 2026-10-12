"""Self-tests for the mutation harness (REQ-005).

The confirmed requirement document declares the mutation contract:

    mutation:
      run: "bash mutation.sh"
      report_path: "reports/mutation/survivors.json"
      format: survivors-json
      max_survivors: 0

These tests pin the parts of that contract that can be checked without paying
for a full mutation run:

* the entry point (``mutation.sh``) and the earlier name
  (``mutation-test.sh``) both exist at the repository root and point at the
  harness;
* every mutation anchor still occurs exactly once in summary.sh, so the harness
  cannot quietly lose a mutant when the source drifts;
* the harness measures at least one mutant, including the mean/sum and the
  minimum/maximum defects the document's REQ-008 names;
* the report writer emits exactly the declared survivors-json shape at the
  declared ``survivors.json`` path, and the earlier ``mutation.json`` name is
  written too;
* the harness runs the delivered CLI tests and excludes only the modules that
  exercise the separate HTTP artifact or the harness itself.

The REL-005 behavioural case runs one real mutant through the delivered CLI
suite, so a suite that could no longer fail is caught here and not only by the
acceptance judge.
"""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

from helpers import ROOT, SCRIPT

HARNESS_SCRIPT = os.path.join(ROOT, "mutation-test.sh")
DECLARED_SCRIPT = os.path.join(ROOT, "mutation.sh")
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

    def test_declared_entry_point_exists_and_runs_the_harness(self):
        # REL-005: the confirmed document declares `bash mutation.sh`; the entry
        # point must be a real, runnable root script pointed at the harness,
        # not just a name in a README.
        self.assertTrue(os.path.isfile(DECLARED_SCRIPT), DECLARED_SCRIPT)
        self.assertTrue(os.access(DECLARED_SCRIPT, os.X_OK), DECLARED_SCRIPT)
        with open(DECLARED_SCRIPT, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("mutation/mutation_test.py", source)
        self.assertIn("reports/mutation/survivors.json", source)

    def test_the_declared_report_path_is_what_the_harness_writes(self):
        self.assertEqual(
            self.harness.DECLARED_REPORT,
            os.path.join(ROOT, "reports", "mutation", "survivors.json"),
        )
        self.assertEqual(
            self.harness.LEGACY_REPORT,
            os.path.join(ROOT, "reports", "mutation", "mutation.json"),
        )
        self.assertIn(self.harness.DECLARED_REPORT, self.harness.REPORT_PATHS)
        self.assertIn(self.harness.LEGACY_REPORT, self.harness.REPORT_PATHS)

    def test_reports_are_written_to_both_canonical_names(self):
        self.assertEqual(
            tuple(self.harness.REPORT_PATHS),
            (self.harness.DECLARED_REPORT, self.harness.LEGACY_REPORT),
        )
        with tempfile.TemporaryDirectory() as directory:
            requested = os.path.join(directory, "requested.json")
            declared = os.path.join(directory, "survivors.json")
            legacy = os.path.join(directory, "mutation.json")
            written = self.harness.write_reports(
                requested, 5, [], mirrors=(declared, legacy)
            )
            self.assertEqual(written, [requested, declared, legacy])
            for path in written:
                with open(path, encoding="utf-8") as handle:
                    self.assertEqual(json.load(handle), {"total": 5, "survivors": []})

    def test_parse_report_defaults_to_the_declared_path_and_resolves_it(self):
        self.assertEqual(self.harness.parse_report([]), self.harness.DECLARED_REPORT)
        self.assertEqual(
            self.harness.parse_report(["--report", "reports/mutation/other.json"]),
            os.path.join(ROOT, "reports", "mutation", "other.json"),
        )
        self.assertEqual(
            self.harness.parse_report(["--report=/tmp/other.json"]),
            "/tmp/other.json",
        )

    def test_unknown_arguments_are_a_usage_error(self):
        with self.assertRaises(SystemExit):
            self.harness.parse_report(["--nonsense"])
        with self.assertRaises(SystemExit):
            self.harness.parse_report(["--report"])

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
        # The entry-point contract module runs `bash mutation.sh`; leaving it
        # in would recurse instead of measuring a mutant.
        self.assertNotIn("test_mutation_entry_point_contract", modules)

    def test_line_of_points_at_the_anchor(self):
        line = self.harness.line_of(self.summary, "if len(row) != 3:")
        self.assertEqual(self.summary.splitlines()[line - 1].strip(), "if len(row) != 3:")

    def test_rel_005_the_catalogue_covers_the_defects_the_document_names(self):
        # REQ-008: the delivered tests must fail when the mean is computed as
        # the sum, and when minimum and maximum are swapped. Those defects must
        # be in the catalogue, or the report could measure mutants that say
        # nothing about the named risk.
        ids = {mutation["id"] for mutation in self.harness.MUTATIONS}
        self.assertTrue({"sum-accumulation", "mean-denominator"} & ids)
        self.assertTrue({"minimum-tracking", "maximum-tracking"} <= ids)

    def test_rel_005_the_delivered_tests_fail_on_a_mutated_behaviour(self):
        # REL-005 is honoured only if the delivered suite can actually fail: a
        # mutant of the aggregation is applied to a throwaway copy and the
        # delivered CLI tests must reject it.
        mutation = next(
            item for item in self.harness.MUTATIONS if item["id"] == "sum-accumulation"
        )
        self.assertEqual(self.summary.count(mutation["old"]), 1)
        work = tempfile.mkdtemp(prefix="takumi-rel-005-")
        try:
            shutil.copytree(
                ROOT, work, dirs_exist_ok=True, ignore=self.harness.COPY_IGNORE
            )
            copy = os.path.join(work, "summary.sh")
            with open(copy, "w", encoding="utf-8") as handle:
                handle.write(self.summary.replace(mutation["old"], mutation["new"], 1))
            self.assertFalse(
                self.harness.run_tests(work),
                "the delivered CLI suite passed a mutant of the aggregation",
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
