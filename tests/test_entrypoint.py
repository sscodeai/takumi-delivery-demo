"""REQ-001: the summary.sh entry point at the repository root."""

import os
import subprocess
import tempfile
import unittest

from helpers import HEADER, ROOT, SCRIPT, run_csv


class EntryPointTests(unittest.TestCase):
    def test_script_exists_at_repository_root(self):
        self.assertTrue(os.path.isfile(SCRIPT))
        self.assertTrue(os.access(SCRIPT, os.R_OK))

    def test_invoked_as_bash_script_with_csv_path(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_missing_argument_is_a_usage_error(self):
        result = subprocess.run(["bash", SCRIPT], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage", result.stderr.lower())

    def test_missing_file_exits_nonzero_with_stderr(self):
        result = subprocess.run(
            ["bash", SCRIPT, os.path.join(ROOT, "does-not-exist.csv")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stderr.strip())

    def test_input_path_is_the_first_positional_argument(self):
        # A path containing spaces must pass through as a single argument and
        # still be read, because the requirement names $1 as the CSV path.
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "daily readings.csv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(HEADER + "2024-01-01,ALPHA,4.5\n")
            result = subprocess.run(
                ["bash", SCRIPT, path], cwd=ROOT, capture_output=True, text=True
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 4.5 4.5 4.5\nSKIPPED 0\nTOTAL 1\n")

    def test_header_only_file_exits_zero(self):
        result = run_csv(HEADER)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "SKIPPED 0\nTOTAL 0\n")

    def test_empty_file_exits_zero(self):
        result = run_csv("")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "SKIPPED 0\nTOTAL 0\n")

    def test_readable_input_with_only_malformed_rows_exits_zero(self):
        result = run_csv(HEADER + "not-a-date,ALPHA,1.0\n")
        self.assertEqual(result.returncode, 0)

    def test_runs_from_a_different_working_directory(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,1.0\n", cwd=os.path.dirname(ROOT))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ALPHA 1 1.0 1.0 1.0\nSKIPPED 0\nTOTAL 1\n")
