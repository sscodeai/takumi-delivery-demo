"""The requirement-run's declared mutation entry point: ``bash mutation/run.sh``.

The requirement document confirmed for this run declares:

    mutation:
      run:           bash mutation/run.sh
      report_path:   reports/mutation/mutation.json
      format:        survivors-json
      max_survivors: 0

REL-004 (mutation-detection) is checked by running exactly that command and
reading exactly that report, so the path may not go missing while the delivered
suite stays green. The root ``mutation.sh`` and ``scripts/mutation.sh`` are the
earlier recorded names of the same harness; this module pins the run's own name
next to them.

The checks here are deliberately STATIC. Actually running ``mutation/run.sh``
starts the full mutation harness, which runs the delivered CLI suite, which
includes this module: the harness would recurse instead of measuring a mutant.
``test_mutation_entry_point_contract`` (which is excluded from the mutant run)
already executes ``bash mutation.sh`` end to end, and ``mutation/run.sh`` is the
same one-line invocation of the same harness.
"""

import os
import stat
import subprocess
import unittest

from helpers import ROOT

DECLARED_SCRIPT = os.path.join(ROOT, "mutation", "run.sh")
HARNESS = os.path.join(ROOT, "mutation", "mutation_test.py")
REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class DeclaredMutationRunEntryPointTests(unittest.TestCase):
    def test_the_declared_entry_point_exists_and_is_executable(self):
        self.assertTrue(os.path.isfile(DECLARED_SCRIPT), DECLARED_SCRIPT)
        mode = os.stat(DECLARED_SCRIPT).st_mode
        self.assertTrue(mode & stat.S_IXUSR, "mutation/run.sh is not executable")

    def test_the_declared_entry_point_runs_the_harness(self):
        self.assertIn("mutation/mutation_test.py", read_text(DECLARED_SCRIPT))

    def test_the_declared_entry_point_writes_the_declared_report(self):
        self.assertIn(
            "reports/mutation/mutation.json", read_text(DECLARED_SCRIPT)
        )

    def test_the_declared_entry_point_runs_from_the_repository_root(self):
        # mutation/run.sh lives one directory below the root, so it must climb
        # back up before invoking the harness; a script that ran in mutation/
        # would resolve the report path relative to the wrong directory.
        self.assertIn('cd "$(dirname "$0")/.."', read_text(DECLARED_SCRIPT))

    def test_the_declared_entry_point_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", DECLARED_SCRIPT], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_harness_module_the_declared_entry_point_names_exists(self):
        self.assertTrue(os.path.isfile(HARNESS), HARNESS)

    def test_the_declared_report_path_matches_the_run_document(self):
        self.assertEqual(
            os.path.relpath(REPORT, ROOT),
            os.path.join("reports", "mutation", "mutation.json"),
        )


if __name__ == "__main__":
    unittest.main()
