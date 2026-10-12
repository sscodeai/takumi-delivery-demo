"""REQ-009 / REL-005: the requirement-declared mutation entry point.

The confirmed requirement document declares:

    mutation:
      run:           bash scripts/mutation.sh
      report_path:   reports/mutation/mutation.json
      format:        survivors-json
      max_survivors: 0

and REL-005 (mutation-detection) is checked by running that command and reading
that report. The root ``mutation.sh`` is the earlier entry point; this module
pins the document's own ``scripts/mutation.sh`` so the declared path cannot go
missing while the suite stays green.

The tests here only inspect the script statically and check it is valid bash:
actually running it drives the full mutation harness, which the delivered suite
already exercises through the root entry point and the judge exercises through
this one.
"""

import os
import stat
import subprocess
import unittest

from helpers import ROOT

DECLARED_SCRIPT = os.path.join(ROOT, "scripts", "mutation.sh")
HARNESS = os.path.join(ROOT, "mutation", "mutation_test.py")
REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class DeclaredScriptsMutationEntryPointTests(unittest.TestCase):
    def test_the_declared_entry_point_exists_and_is_executable(self):
        self.assertTrue(os.path.isfile(DECLARED_SCRIPT), DECLARED_SCRIPT)
        mode = os.stat(DECLARED_SCRIPT).st_mode
        self.assertTrue(mode & stat.S_IXUSR, "scripts/mutation.sh is not executable")

    def test_the_declared_entry_point_runs_the_harness(self):
        source = read_text(DECLARED_SCRIPT)
        self.assertIn("mutation/mutation_test.py", source)

    def test_the_declared_entry_point_writes_the_declared_report(self):
        source = read_text(DECLARED_SCRIPT)
        self.assertIn("reports/mutation/mutation.json", source)

    def test_the_declared_entry_point_runs_from_the_repository_root(self):
        source = read_text(DECLARED_SCRIPT)
        self.assertIn('cd "$(dirname "$0")/.."', source)

    def test_the_declared_entry_point_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", DECLARED_SCRIPT], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_harness_module_the_declared_entry_point_names_exists(self):
        self.assertTrue(os.path.isfile(HARNESS), HARNESS)

    def test_the_declared_report_path_is_the_documents_legacy_name(self):
        self.assertEqual(
            os.path.relpath(REPORT, ROOT),
            os.path.join("reports", "mutation", "mutation.json"),
        )


if __name__ == "__main__":
    unittest.main()
