"""Tests bound directly to the confirmed requirement document.

Every assertion below reads ``docs/requirements/intake.yaml`` and drives the
entry point the document declares, so a document change that the deliverable no
longer satisfies fails here by name.  It covers the confirmation the run is
bound to:

* the declared ``deliverable.run`` command (REQ-001),
* the headerless ``input_format.sample`` world (REQ-005 / AMB-005),
* the declared station, skipped and total line shapes (REQ-002/003/004),
* REL-005 mutation-detection: the mutation anchors the delivered coverage
  depends on must exist exactly once, and the harness must target real test
  modules.

The document is read as text, not through a YAML library: the environment has
only the Python 3 standard library, and the two keys this module needs
(``deliverable.run`` and ``input_format.sample``) have a stable, indented shape.
"""

import importlib.util
import os
import re
import shlex
import subprocess
import unittest

from helpers import HEADER, ROOT, STATION_SHAPE, run_csv
from reference import reference_output

DOCUMENT = os.path.join(ROOT, "docs", "requirements", "intake.yaml")
SUMMARY = os.path.join(ROOT, "summary.sh")
MUTATION_MODULE = os.path.join(ROOT, "mutation", "mutation_test.py")
MUTATION_RUNNER = os.path.join(ROOT, "mutation", "run.sh")
TESTS_DIR = os.path.join(ROOT, "tests")

SKIPPED_SHAPE = re.compile(r"^SKIPPED [0-9]+$")
TOTAL_SHAPE = re.compile(r"^TOTAL [0-9]+$")
SAMPLE_LINE = re.compile(r"^-?[0-9]+\.[0-9]$")


def read_document():
    with open(DOCUMENT, "r", encoding="utf-8") as handle:
        return handle.read()


def declared_sample(text):
    """Return the ``input_format.sample`` CSV block from the document text."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "sample: |":
            start = index + 1
            break
    if start is None:
        raise AssertionError("the document declares no input_format.sample block")

    block = []
    for line in lines[start:]:
        if line.strip() == "":
            block.append("")
            continue
        if not line.startswith("      "):
            break
        block.append(line)
    while block and block[-1].strip() == "":
        block.pop()
    if not block:
        raise AssertionError("the declared input_format.sample block is empty")

    indent = len(block[0]) - len(block[0].lstrip(" "))
    return "\n".join(line[indent:] for line in block) + "\n"


def declared_run(text):
    """Return the ``deliverable.run`` command string from the document text."""
    deliverable = text.index("deliverable:")
    match = re.search(r'(?m)^\s*run:\s*"([^"]+)"', text[deliverable:])
    if match is None:
        raise AssertionError("the document declares no deliverable.run command")
    return match.group(1)


class DeclaredDeliverableTests(unittest.TestCase):
    """REQ-001 and REQ-005: the document names the command and the world."""

    def test_document_declares_the_summary_entry_point(self):
        command = declared_run(read_document())
        self.assertIn("summary.sh", command)
        self.assertIn("{csv}", command)

    def test_the_declared_command_runs_the_readable_sample_with_exit_zero(self):
        command = declared_run(read_document())
        sample = declared_sample(read_document())
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        try:
            handle.write(sample)
            handle.close()
            argv = [part.replace("{csv}", handle.name) for part in shlex.split(command)]
            result = subprocess.run(
                argv, cwd=ROOT, capture_output=True, text=True, timeout=120
            )
        finally:
            os.unlink(handle.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip())

    def test_declared_sample_is_the_headerless_world(self):
        # AMB-005 (no-header): the sample begins with a reading, not the
        # declared column names, so the tool must not drop it as a header.
        sample = declared_sample(read_document())
        first = sample.splitlines()[0]
        self.assertNotEqual(first, HEADER.rstrip("\n"))
        self.assertNotIn("station", first)
        self.assertEqual(len(first.split(",")), 3)

    def test_declared_sample_is_aggregated_exactly(self):
        sample = declared_sample(read_document())
        result = run_csv(sample)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout,
            "ALPHA 3 9.5 11.6 10.5\n"
            "BRAVO 2 -2.5 -1.5 -2.0\n"
            "SKIPPED 0\n"
            "TOTAL 5\n",
        )

    def test_declared_sample_matches_the_independent_reference(self):
        sample = declared_sample(read_document())
        result = run_csv(sample)
        self.assertEqual(result.stdout, reference_output(sample))

    def test_declared_output_shapes_are_printed(self):
        sample = declared_sample(read_document())
        result = run_csv(sample)
        lines = [line for line in result.stdout.splitlines() if line]
        stations = [
            line for line in lines if not line.startswith(("SKIPPED ", "TOTAL "))
        ]
        skipped = [line for line in lines if line.startswith("SKIPPED ")]
        totals = [line for line in lines if line.startswith("TOTAL ")]

        self.assertEqual(len(stations), 2)
        for line in stations:
            self.assertRegex(line, STATION_SHAPE)
            for token in line.split(" ")[2:]:
                self.assertRegex(token, SAMPLE_LINE)
        self.assertEqual(len(skipped), 1)
        self.assertRegex(skipped[0], SKIPPED_SHAPE)
        self.assertEqual(len(totals), 1)
        self.assertRegex(totals[0], TOTAL_SHAPE)


class MutationHarnessTests(unittest.TestCase):
    """REL-005: the delivered tests must fail when the behaviour is mutated."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "mutation_test", MUTATION_MODULE
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.mutations = module.MUTATIONS
        cls.cli_modules = module.CLI_TEST_MODULES

    def test_the_harness_has_at_least_one_mutation(self):
        self.assertTrue(self.mutations)

    def test_every_mutation_anchor_exists_exactly_once_in_the_deliverable(self):
        with open(SUMMARY, "r", encoding="utf-8") as handle:
            source = handle.read()
        for mutation in self.mutations:
            with self.subTest(mutation=mutation["id"]):
                self.assertEqual(
                    source.count(mutation["old"]),
                    1,
                    "mutation anchor is not unique in summary.sh: %s"
                    % mutation["description"],
                )

    def test_the_harness_targets_real_cli_test_modules(self):
        for name in self.cli_modules:
            with self.subTest(module=name):
                path = os.path.join(TESTS_DIR, name + ".py")
                self.assertTrue(os.path.isfile(path), path)

    def test_the_runner_is_a_discoverable_bash_entry_point(self):
        self.assertTrue(os.path.isfile(MUTATION_RUNNER))
        result = subprocess.run(
            ["bash", "-n", MUTATION_RUNNER], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
