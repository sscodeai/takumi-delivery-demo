"""Document-driven traceability for docs/requirements/intake.yaml.

The focused suites pin behaviour; this layer checks the suite against the
confirmed document itself, so a requirement or a settled ambiguity cannot slip
in without any test naming it:

* every ``REQ-nnn`` acceptance criterion and every ``AMB-nnn`` decision the
  document declares is referenced by at least one test module under ``tests/``;
* the report always carries exactly one ``SKIPPED`` line and exactly one
  ``TOTAL`` line, whatever the fixture;
* the input path is taken from ``$1`` and extra positional arguments are
  harmless (REQ-001 says no other arguments are required).
"""

import os
import re
import subprocess
import unittest

from helpers import HEADER, ROOT, SCRIPT, run_csv, skipped_of, total_of

DOC = os.path.join(ROOT, "docs", "requirements", "intake.yaml")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

ID_RE = re.compile(r"^\s*-\s*id:\s*(REQ-\d{3}|AMB-\d{3})\s*$", re.MULTILINE)

EXPECTED_REQUIREMENTS = {"REQ-%03d" % index for index in range(1, 10)}
EXPECTED_AMBIGUITIES = {"AMB-%03d" % index for index in range(1, 6)}


def declared_ids():
    with open(DOC, encoding="utf-8") as handle:
        return set(ID_RE.findall(handle.read()))


def test_sources():
    for name in sorted(os.listdir(TESTS_DIR)):
        if name.startswith("test_") and name.endswith(".py"):
            with open(os.path.join(TESTS_DIR, name), encoding="utf-8") as handle:
                yield name, handle.read()


class DocumentTraceabilityTests(unittest.TestCase):
    def test_the_document_declares_every_expected_id(self):
        ids = declared_ids()
        self.assertTrue(EXPECTED_REQUIREMENTS <= ids, EXPECTED_REQUIREMENTS - ids)
        self.assertTrue(EXPECTED_AMBIGUITIES <= ids, EXPECTED_AMBIGUITIES - ids)

    def test_every_declared_id_is_named_by_a_test_module(self):
        # A declared id that no test module names has no traceable coverage.
        ids = declared_ids()
        sources = list(test_sources())
        for identifier in sorted(ids):
            with self.subTest(identifier=identifier):
                naming = [
                    name for name, source in sources if identifier in source
                ]
                self.assertTrue(
                    naming, "%s is not named by any test module" % identifier
                )

    def test_every_requirement_has_a_behavioural_test_method(self):
        # Each REQ-nnn is pinned by a test method that carries the id in its
        # name (acceptance matrix or focused suite), not just in a docstring.
        method_ids = set()
        for _name, source in test_sources():
            method_ids.update(re.findall(r"def test_(req_\d{3})", source))
        for identifier in sorted(EXPECTED_REQUIREMENTS):
            with self.subTest(identifier=identifier):
                lowered = identifier.lower().replace("-", "_")
                self.assertIn(lowered, method_ids)


class UniversalReportInvariantTests(unittest.TestCase):
    """SKIPPED and TOTAL are always present exactly once, on any fixture."""

    FIXTURES = {
        "empty": "",
        "header-only": HEADER,
        "valid": HEADER + "2024-01-01,ALPHA,1.0\n",
        "malformed-only": HEADER + "not-a-date,ALPHA,1.0\n",
        "mixed": (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA,2.0\n"
            + "2024-01-02,,3.0\n"
            + "bad,ALPHA,4.0\n"
        ),
    }

    def test_one_skipped_and_one_total_line_on_every_fixture(self):
        for name, text in self.FIXTURES.items():
            with self.subTest(fixture=name):
                result = run_csv(text)
                self.assertEqual(result.returncode, 0)
                lines = result.stdout.splitlines()
                self.assertEqual(
                    sum(line.startswith("SKIPPED ") for line in lines), 1
                )
                self.assertEqual(sum(line.startswith("TOTAL ") for line in lines), 1)
                self.assertEqual(lines[-2].split(" ")[0], "SKIPPED")
                self.assertEqual(lines[-1].split(" ")[0], "TOTAL")

    def test_skipped_and_total_never_go_negative(self):
        for name, text in self.FIXTURES.items():
            with self.subTest(fixture=name):
                result = run_csv(text)
                self.assertGreaterEqual(skipped_of(result.stdout), 0)
                self.assertGreaterEqual(total_of(result.stdout), 0)


class PositionalArgumentTests(unittest.TestCase):
    """REQ-001: the CSV path is $1 and no other argument is required."""

    def test_extra_positional_arguments_are_ignored(self):
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        path = handle.name
        handle.write(HEADER + "2024-01-01,ALPHA,7.5\n")
        handle.close()
        try:
            result = subprocess.run(
                ["bash", SCRIPT, path, "ignored", "--another"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 7.5 7.5 7.5\nSKIPPED 0\nTOTAL 1\n")


if __name__ == "__main__":
    unittest.main()
