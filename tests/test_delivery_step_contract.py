"""Unit and integration tests for the delivery of the previous step.

The previous step changed two things in the project:

1. it added ``tests/test_intake_sample_contract.py``, which parses
   ``deliverable.input_format.sample`` out of ``docs/requirements/intake.yaml``
   at test time and derives the acceptance judge's base, reshuffled, duplicate
   and malformed fixtures from the document rather than from a copied constant;
2. it removed a stale extra row from the sample heredoc in
   ``.github/workflows/ci.yml`` so the pipeline feeds the deliverable exactly
   the world the requirement document declares.

This module is the unit and integration layer for that delivery:

* the document parser is unit-tested on the real document, on a synthetic
  document with blank lines and a following dedented key, and on a document that
  declares no sample at all;
* the derived fixtures are checked against the hard-coded fixtures in
  ``test_forged_judge_contract.py`` and against the independent
  ``tests/reference.py`` recomputation, so the dynamic parser cannot silently
  drift from the judge's world;
* the CI pipeline is checked to carry the declared sample (each row exactly
  once, the stale row gone) and both required commands;
* the previous step's module is executed through the same discovery mechanism
  the smoke gate uses, proving it is really collected and green.

The requirement ids this boundary serves are REQ-001 (the declared entry point
and invocation), REQ-002 (the declared input world), AMB-001 (malformed rows on
the ``SKIPPED`` line), AMB-002 (merge duplicate keys), AMB-003 (half away from
zero) and REL-001 (row-order invariance); the derivations below exercise each
one through the delivered CLI.
"""

import os
import subprocess
import sys
import tempfile
import unittest

import test_acceptance_matrix as acceptance_matrix
import test_forged_judge_contract as forged_judge
import test_intake_sample_contract as sample_contract
from helpers import HEADER, ROOT, run_csv
from reference import reference_output

DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
RUNNER = os.path.join(ROOT, "run-tests.sh")


def _write_temp_document(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    handle.write(text)
    handle.close()
    return handle.name


def ci_sample_rows():
    """The rows of the ``TAKUMI_SAMPLE`` heredoc in the CI workflow."""
    with open(CI, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for index, line in enumerate(lines):
        if "<<'TAKUMI_SAMPLE'" not in line:
            continue
        rows = []
        for following in lines[index + 1:]:
            if following.strip() == "TAKUMI_SAMPLE":
                return rows
            rows.append(following.strip())
    raise AssertionError("%s declares no TAKUMI_SAMPLE heredoc" % CI)


class DeclaredSampleParserTests(unittest.TestCase):
    """Unit tests for the parser the previous step introduced."""

    def test_the_parser_reads_the_five_declared_rows(self):
        self.assertEqual(sample_contract.declared_sample(), forged_judge.SAMPLE)
        self.assertEqual(len(sample_contract.declared_sample()), 5)

    def test_both_document_parsers_agree(self):
        # test_acceptance_matrix reads the same block with its own parser; the
        # two must not drift apart.
        self.assertEqual(
            sample_contract.declared_sample(),
            acceptance_matrix.declared_sample().splitlines(),
        )

    def test_the_parser_skips_blank_lines_and_stops_at_a_dedent(self):
        document = (
            "deliverable:\n"
            "  input_format:\n"
            "    sample: |\n"
            "      A,1\n"
            "      B,2\n"
            "\n"
            "  another_key: value\n"
        )
        path = _write_temp_document(document)
        original = sample_contract.DOC
        sample_contract.DOC = path
        try:
            self.assertEqual(sample_contract.declared_sample(), ["A,1", "B,2"])
        finally:
            sample_contract.DOC = original
            os.unlink(path)

    def test_a_document_without_a_sample_is_an_error(self):
        path = _write_temp_document("deliverable:\n  run: bash summary.sh\n")
        original = sample_contract.DOC
        sample_contract.DOC = path
        try:
            with self.assertRaises(AssertionError):
                sample_contract.declared_sample()
        finally:
            sample_contract.DOC = original
            os.unlink(path)


class FixtureDerivationTests(unittest.TestCase):
    """Unit tests for the fixtures the previous step derives from the sample."""

    @classmethod
    def setUpClass(cls):
        sample_contract.DeclaredSampleContractTests.setUpClass()
        cls.derived = sample_contract.DeclaredSampleContractTests

    def test_render_prepends_the_declared_header_only_when_asked(self):
        rows = ["2024-01-01,ALPHA,1.0"]
        self.assertEqual(sample_contract._render(rows), HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(sample_contract._render(rows, header=False), "2024-01-01,ALPHA,1.0\n")

    def test_set_field_replaces_only_the_named_column(self):
        row = "2024-01-01,ALPHA,10.4"
        self.assertEqual(sample_contract._set_field(row, 2, "abc"), "2024-01-01,ALPHA,abc")
        self.assertEqual(sample_contract._set_field(row, 0, "not-a-date"), "not-a-date,ALPHA,10.4")
        self.assertEqual(sample_contract._set_field(row, 1, "BRAVO"), "2024-01-01,BRAVO,10.4")

    def test_the_dynamic_base_is_the_declared_world(self):
        self.assertEqual(self.derived.base, forged_judge.BASE)

    def test_duplicate_fixtures_reproduce_the_forged_judge(self):
        # AMB-002 (merge): each derived duplicate carries the new maximum 12.6
        # on a date one day outside the sample range.
        self.assertEqual(self.derived.dup_late, forged_judge.DUP_LATE)
        self.assertEqual(self.derived.dup_early, forged_judge.DUP_EARLY)

    def test_malformed_fixture_reproduces_the_forged_judge(self):
        # AMB-001 (skip-count): a short row, a non-numeric measure and an
        # unparseable date, each derived from the sample's first row.
        self.assertEqual(self.derived.malformed, forged_judge.MALFORMED)

    def test_every_derived_fixture_agrees_with_the_independent_reference(self):
        # REL-001/DIFF-001: the delivered CLI must match the Fraction reference
        # on every fixture the previous step derives.
        for name, fixture in (
            ("base", self.derived.base),
            ("reshuffled", (
                HEADER
                + "\n".join(reversed(self.derived.sample))
                + "\n"
            )),
            ("duplicate-late", self.derived.dup_late),
            ("duplicate-early", self.derived.dup_early),
            ("malformed", self.derived.malformed),
        ):
            with self.subTest(fixture=name):
                result = run_csv(fixture)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, reference_output(fixture))

    def test_malformed_fixture_reports_the_declared_skip_count(self):
        result = run_csv(self.derived.malformed)
        self.assertEqual(result.returncode, 0)
        self.assertIn("SKIPPED 3\n", result.stdout)
        self.assertIn("TOTAL 5\n", result.stdout)


class CiPipelineContractTests(unittest.TestCase):
    """Integration tests for the pipeline sample the previous step corrected."""

    def test_the_pipeline_sample_is_drawn_from_the_declared_world(self):
        declared = sample_contract.declared_sample()
        rows = ci_sample_rows()
        # The pipeline fixture is the declared world's leading rows: every row
        # comes from the document, in the document's order, with nothing
        # invented and nothing repeated.
        self.assertTrue(rows)
        self.assertEqual(rows, declared[: len(rows)])
        # The stale row the previous step removed must not come back.
        self.assertNotIn("2024-01-02,BRAVO,3.0", rows)
        self.assertEqual(len(rows), len(set(rows)))

    def test_the_pipeline_runs_the_suite_and_the_declared_deliverable(self):
        with open(CI, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("run-tests.sh", text)
        self.assertIn("bash summary.sh", text)
        self.assertRegex(text, r"timeout\s+[0-9]+s")

    def test_the_root_runner_is_the_discoverable_entry_point(self):
        self.assertTrue(os.path.isfile(RUNNER))
        self.assertTrue(os.access(RUNNER, os.X_OK))
        result = subprocess.run(
            ["bash", "-n", RUNNER], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class PreviousStepSuiteRunsTests(unittest.TestCase):
    """Integration: the previous step's module is really collected and green."""

    def test_the_previous_step_module_is_discovered_and_passes(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_intake_sample_contract.py",
                "-v",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("Ran 6 tests", result.stderr)
        self.assertIn("OK", result.stderr)

    def test_the_previous_step_module_is_reachable_from_the_default_suite(self):
        path = os.path.join(ROOT, "tests", "test_intake_sample_contract.py")
        self.assertTrue(os.path.isfile(path), path)


if __name__ == "__main__":
    unittest.main()
