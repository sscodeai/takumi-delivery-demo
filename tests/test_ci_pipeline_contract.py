"""Unit and integration tests for the previous step's pipeline repair.

The previous step (commit ``ci: keep the declared sample and the mutation gate
in the pipeline``) corrected ``.github/workflows/ci.yml`` so the pipeline again
matches ``docs/requirements/intake.yaml``:

1. the ``TAKUMI_SAMPLE`` heredoc once more feeds the deliverable exactly the
   document's declared world -- all five rows under
   ``deliverable.input_format.sample``, in the document's order, with the two
   earlier-missing rows (``2024-01-02,BRAVO,-1.5`` and ``2024-01-03,ALPHA,9.5``)
   restored;
2. a new step asserts the deliverable's exact report for that world;
3. the declared mutation gate is restored, running ``bash mutation.sh`` and
   writing ``reports/mutation/survivors.json``.

Nothing pinned those three changes, so a regenerated workflow could drop them
again (as it had) while the delivered suite stayed green.  This module is the
unit and integration layer for the repair: it reads the declared world out of
the confirmed document rather than a copied constant, checks the pipeline
against it, and runs the deliverable on that world for real.

The acceptance criteria this boundary exercises through the pipeline are
REQ-001 (the root entry point and its invocation), REQ-002 (the declared input
world), REQ-003/REQ-004 (the exact station and TOTAL lines), REQ-005/AMB-001
(malformed rows on the ``SKIPPED`` line), AMB-002 (merge duplicate keys),
AMB-003 (half away from zero), AMB-004 (ascending byte-wise order), AMB-005
(valid-only TOTAL) and REL-001 (row-order invariance).
"""

import os
import re
import unittest

import test_intake_sample_contract as sample_contract
from helpers import ROOT, run_csv
from reference import reference_output

CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")

# The exact report the declared (header-less) sample must produce; the document
# declares the world and relations, so this text is derived below and only
# pinned here as the pipeline's declared expectation.
DECLARED_REPORT = [
    "ALPHA 3 9.5 11.6 10.5",
    "BRAVO 2 -2.5 -1.5 -2.0",
    "SKIPPED 0",
    "TOTAL 5",
]


def workflow_text():
    with open(CI, encoding="utf-8") as handle:
        return handle.read()


def heredoc(name):
    """Return the stripped lines of the ``<<'name'`` heredoc in the workflow.

    The workflow indents every heredoc body inside its ``run: |`` block, so the
    lines are stripped to recover the text the shell actually feeds the
    deliverable.
    """
    lines = workflow_text().splitlines()
    for index, line in enumerate(lines):
        if "<<'%s'" % name not in line:
            continue
        collected = []
        for following in lines[index + 1:]:
            if following.strip() == name:
                return collected
            collected.append(following.strip())
    raise AssertionError("%s declares no %s heredoc" % (CI, name))


def ci_sample_rows():
    return heredoc("TAKUMI_SAMPLE")


def ci_expected_report():
    return heredoc("TAKUMI_EXPECTED")


class DeclaredWorldParserTests(unittest.TestCase):
    """Unit tests for the declared world and the heredoc parser."""

    def test_the_document_still_declares_the_five_row_world(self):
        # The parser is the same one the previous step's module introduced; a
        # change to the document reaches these tests instead of a stale copy.
        rows = sample_contract.declared_sample()
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(len(row.split(",")), 3)

    def test_the_heredoc_parser_reads_a_known_block(self):
        self.assertEqual(
            heredoc("TAKUMI_EXPECTED"), ci_expected_report()
        )
        self.assertTrue(ci_sample_rows())

    def test_the_heredoc_parser_fails_closed_on_a_missing_heredoc(self):
        with self.assertRaises(AssertionError):
            heredoc("TAKUMI_DOES_NOT_EXIST")

    def test_the_pipeline_sample_is_exactly_the_declared_world(self):
        # The previous step's whole point: the pipeline carries the document's
        # world, in order, with nothing invented, dropped or repeated.
        declared = sample_contract.declared_sample()
        rows = ci_sample_rows()
        self.assertEqual(rows, declared)
        self.assertEqual(len(rows), len(set(rows)))
        # The two rows the removed drift left out are back.
        self.assertIn("2024-01-02,BRAVO,-1.5", rows)
        self.assertIn("2024-01-03,ALPHA,9.5", rows)
        # The stale, invented row must not come back.
        self.assertNotIn("2024-01-02,BRAVO,3.0", rows)

    def test_the_declared_world_is_header_less_like_the_document(self):
        # The document's sample block carries no header line, so the pipeline
        # must not add one; the deliverable reads it positionally.
        rows = ci_sample_rows()
        self.assertFalse(any(row.split(",")[0].strip().lower() == "date" for row in rows))

    def test_the_reference_recomputes_the_pipeline_expectation(self):
        # REL-002/REL-003/REL-004/DIFF-001: an independent Fraction
        # recomputation of the declared world must equal the text the pipeline
        # pins, so the expectation is not a hand-maintained guess.
        text = "\n".join(ci_sample_rows()) + "\n"
        self.assertEqual(reference_output(text).splitlines(), ci_expected_report())

    def test_the_pipeline_expectation_is_the_declared_report(self):
        self.assertEqual(ci_expected_report(), DECLARED_REPORT)
        # Exactly one SKIPPED line and exactly one TOTAL line.
        self.assertEqual(
            sum(line.startswith("SKIPPED ") for line in ci_expected_report()), 1
        )
        self.assertEqual(
            sum(line.startswith("TOTAL ") for line in ci_expected_report()), 1
        )

    def test_each_station_line_carries_one_decimal_place(self):
        # REQ-003: <station> <count> <min> <max> <mean> with one decimal.
        shape = re.compile(r"^\S+ [0-9]+ -?[0-9]+\.[0-9] -?[0-9]+\.[0-9] -?[0-9]+\.[0-9]$")
        station = [
            line
            for line in ci_expected_report()
            if not line.startswith(("SKIPPED ", "TOTAL "))
        ]
        self.assertEqual(len(station), 2)
        for line in station:
            self.assertRegex(line, shape)


class PipelineWiringTests(unittest.TestCase):
    """Integration tests for the three changes the previous step made."""

    def test_the_pipeline_runs_the_projects_own_suite(self):
        self.assertIn("run-tests.sh", workflow_text())

    def test_the_pipeline_writes_the_declared_sample_and_runs_it(self):
        text = workflow_text()
        self.assertIn("TAKUMI_SAMPLE", text)
        self.assertIn("bash summary.sh takumi-sample.csv", text)
        self.assertRegex(text, r"timeout\s+[0-9]+s")

    def test_the_pipeline_checks_the_deliverables_exact_report(self):
        # The new step the previous step added: diff the run against the
        # expected report, so a wrong station, count, rounding or TOTAL fails
        # the pipeline instead of only the local suite.
        text = workflow_text()
        self.assertIn("TAKUMI_EXPECTED", text)
        self.assertIn("diff -u expected.txt report.txt", text)

    def test_the_pipeline_restores_the_declared_mutation_gate(self):
        # The declared gate the previous step restored: `bash mutation.sh`
        # against the declared survivors-json report path.
        text = workflow_text()
        self.assertRegex(text, r"(?m)^\s{2}mutation:\s*$")
        self.assertIn("bash mutation.sh", text)
        self.assertIn("reports/mutation/survivors.json", text)

    def test_the_pipeline_declares_the_three_expected_jobs(self):
        text = workflow_text()
        for job in ("tests:", "deliverable:", "mutation:"):
            with self.subTest(job=job):
                self.assertRegex(text, r"(?m)^\s{2}%s\s*$" % re.escape(job))


class DeclaredWorldIntegrationTests(unittest.TestCase):
    """Integration: run the deliverable on the pipeline's declared world."""

    def test_running_the_deliverable_prints_the_pipeline_report(self):
        text = "\n".join(ci_sample_rows()) + "\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines(), ci_expected_report())

    def test_the_pipeline_report_matches_the_independent_reference(self):
        text = "\n".join(ci_sample_rows()) + "\n"
        result = run_csv(text)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, reference_output(text))

    def test_reversing_the_declared_world_keeps_the_output_identical(self):
        # REL-001: the pipeline's expectation is only stable if the world is
        # aggregated as a multiset, not in file order.
        rows = ci_sample_rows()
        forward = run_csv("\n".join(rows) + "\n")
        backward = run_csv("\n".join(reversed(rows)) + "\n")
        self.assertEqual(forward.returncode, 0)
        self.assertEqual(backward.returncode, 0)
        self.assertEqual(forward.stdout, backward.stdout)
        self.assertEqual(forward.stdout.splitlines(), ci_expected_report())


if __name__ == "__main__":
    unittest.main()
