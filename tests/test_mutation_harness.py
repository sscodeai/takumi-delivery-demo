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
import threading
import time
import unittest
from unittest import mock

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
        # in would recurse instead of measuring a mutant. The integration
        # module runs `bash mutation/run.sh`, so it is excluded for the same
        # reason.
        self.assertNotIn("test_mutation_entry_point_contract", modules)
        self.assertNotIn("test_mutation_run_integration", modules)

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


class MutationConcurrencyUnitTests(unittest.TestCase):
    """Unit tests for the previous step's concurrent mutant runner.

    The perf step split the sequential per-mutant loop into
    ``mutation_workers``/``run_mutation``/``run_mutations`` so mutants run in
    parallel against private copies. Those helpers are pinned here directly so
    a regression that serialises the pool, drops a verdict, reorders the report
    or shares one copy is caught without paying for a full mutation run. This
    module is excluded from the mutation gate itself, so the extra checks cost
    the gate nothing.
    """

    def setUp(self):
        self.harness = load_harness()

    def test_mutation_workers_is_bounded_by_pending_mutants_and_the_cap(self):
        self.assertEqual(self.harness.mutation_workers(0), 1)
        for count in range(1, 9):
            with self.subTest(count=count):
                workers = self.harness.mutation_workers(count)
                self.assertGreaterEqual(workers, 1)
                self.assertLessEqual(workers, count)
        # A catalogue far larger than any runner is capped, never unbounded.
        self.assertLessEqual(self.harness.mutation_workers(10000), 8)

    def test_mutation_workers_honours_the_cpu_count(self):
        with mock.patch.object(self.harness.os, "cpu_count", return_value=2):
            self.assertEqual(self.harness.mutation_workers(100), min(100, 4, 8))
        # A platform that cannot report the core count still gets a usable pool.
        with mock.patch.object(self.harness.os, "cpu_count", return_value=None):
            self.assertEqual(self.harness.mutation_workers(100), min(100, 3, 8))

    def test_run_mutations_short_circuits_an_empty_catalogue(self):
        def explode(*_args):
            raise AssertionError("run_mutation must not be called for no mutants")

        self.harness.run_mutation = explode
        with tempfile.TemporaryDirectory() as work_root:
            self.assertEqual(
                self.harness.run_mutations("pristine", [], work_root), []
            )

    def test_run_mutations_returns_verdicts_in_input_order(self):
        mutations = [
            {"id": "slow", "old": "a", "new": "b"},
            {"id": "fast", "old": "c", "new": "d"},
            {"id": "middle", "old": "e", "new": "f"},
        ]
        delays = {"slow": 0.20, "fast": 0.0, "middle": 0.05}

        def delayed(_pristine, mutation, _work_root):
            time.sleep(delays[mutation["id"]])
            return mutation["id"] == "middle"

        self.harness.run_mutation = delayed
        with tempfile.TemporaryDirectory() as work_root:
            outcomes = self.harness.run_mutations("pristine", mutations, work_root)
        # Completion order is fast, middle, slow; the report order must stay the
        # catalogue order so the survivors list is deterministic.
        self.assertEqual(outcomes, [False, False, True])

    def test_run_mutations_overlaps_the_mutants(self):
        mutations = [
            {"id": "m%d" % index, "old": "a", "new": "b"} for index in range(4)
        ]
        rendezvous = threading.Barrier(len(mutations))
        timeouts = []

        def wait_for_peers(_pristine, mutation, _work_root):
            try:
                rendezvous.wait(timeout=10)
            except threading.BrokenBarrierError:
                timeouts.append(mutation["id"])
            return True

        self.harness.mutation_workers = lambda count: len(mutations)
        self.harness.run_mutation = wait_for_peers
        with tempfile.TemporaryDirectory() as work_root:
            outcomes = self.harness.run_mutations("pristine", mutations, work_root)
        self.assertEqual(timeouts, [], "mutants did not run concurrently")
        self.assertEqual(outcomes, [True] * len(mutations))

    def test_run_mutations_gives_every_mutant_a_private_mutated_copy(self):
        mutations = [
            {
                "id": "first",
                "old": "if len(row) != 3:",
                "new": "if len(row) < 3:",
            },
            {
                "id": "second",
                "old": "entry[3] += value",
                "new": "entry[3] -= value",
            },
        ]
        with open(SCRIPT, encoding="utf-8") as handle:
            pristine = handle.read()
        copies = {}

        def capture(worktree):
            with open(
                os.path.join(worktree, "summary.sh"), encoding="utf-8"
            ) as handle:
                copies[worktree] = handle.read()
            # One mutant survives, one is killed: the verdicts must not leak.
            return os.path.basename(worktree) == "mutant-second"

        self.harness.run_tests = capture
        with tempfile.TemporaryDirectory() as work_root:
            outcomes = self.harness.run_mutations(pristine, mutations, work_root)
            first = copies[os.path.join(work_root, "mutant-first")]
            second = copies[os.path.join(work_root, "mutant-second")]
        self.assertEqual(outcomes, [False, True])
        self.assertEqual(len(copies), 2, "each mutant needs its own copy")
        self.assertIn("if len(row) < 3:", first)
        self.assertNotIn("if len(row) != 3:", first)
        self.assertIn("entry[3] -= value", second)
        self.assertNotIn("entry[3] += value", second)
        # The real deliverable was never touched.
        with open(SCRIPT, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), pristine)


if __name__ == "__main__":
    unittest.main()
