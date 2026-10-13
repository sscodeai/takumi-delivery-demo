"""Robustness and failure-contract unit and integration tests for summary.sh.

The focused suites pin the happy path and the malformed-row classes.  This
module covers the edges those suites leave implicit, at the same process
boundary the requirement document names (``bash summary.sh <csv>``):

* REQ-008 -- a missing, unreadable or directory input fails with a non-zero
  status, writes its diagnostic to stderr and writes NOTHING to stdout;
* REQ-002 / REQ-005 / AMB-001 -- a parseable but pathological numeric field
  (thousands of digits) is rendered rather than aborting the run;
* REQ-002 -- non-ASCII station ids are aggregated, and an undecodable byte is
  replaced rather than crashing the run;
* REQ-007 / AMB-004 -- non-ASCII station ids are still ordered byte-wise;
* AMB-003 -- a negative zero reading normalises to ``0.0``.

These are the paths inside ``summary.sh`` (``set_int_max_str_digits``,
``errors="replace"``, the ``OSError`` handler and the ``render_one_decimal``
zero branch) that no other module exercises end to end.
"""

import os
import subprocess
import tempfile
import unittest

from helpers import HEADER, ROOT, SCRIPT, run_csv, station_lines, total_of

HUGE = "9" * 5000


def write_bytes(data):
    handle = tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False)
    handle.write(data)
    handle.close()
    return handle.name


class UnreadableInputTests(unittest.TestCase):
    """REQ-008: an unreadable input fails loudly and prints no report."""

    def test_req_008_a_missing_file_exits_nonzero_with_only_a_stderr_diagnostic(self):
        missing = os.path.join(tempfile.gettempdir(), "takumi-robustness-missing.csv")
        self.assertFalse(os.path.exists(missing))
        result = subprocess.run(
            ["bash", SCRIPT, missing],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("cannot read", result.stderr)

    def test_req_008_a_directory_input_fails_loudly(self):
        directory = tempfile.mkdtemp(prefix="takumi-robustness-dir-")
        try:
            result = subprocess.run(
                ["bash", SCRIPT, directory],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
        finally:
            os.rmdir(directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertNotEqual(result.stderr.strip(), "")

    def test_req_008_no_argument_is_refused_with_a_usage_line(self):
        result = subprocess.run(
            ["bash", SCRIPT],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("usage", result.stderr.lower())


class PathologicalValueTests(unittest.TestCase):
    """REQ-002 / REQ-005 / AMB-001: odd but well-formed fields never abort."""

    def test_req_005_a_thousands_of_digits_temperature_is_rendered(self):
        # Python 3.11 caps int-to-str at 4300 digits by default; summary.sh
        # raises that cap, so a 5000-digit reading must render, not raise.
        text = (
            HEADER
            + "2024-01-01,ALPHA,%s\n" % HUGE
            + "2024-01-02,ALPHA,1.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = station_lines(result.stdout)
        self.assertEqual(len(lines), 1)
        station, count, minimum, maximum, mean = lines[0].split(" ")
        self.assertEqual(station, "ALPHA")
        self.assertEqual(count, "2")
        self.assertEqual(minimum, "1.0")
        self.assertEqual(maximum, HUGE + ".0")
        self.assertEqual(mean, "5" + "0" * 4999 + ".0")
        self.assertEqual(total_of(result.stdout), 2)

    def test_req_002_a_very_long_field_is_not_a_parser_error(self):
        # The csv field-size limit is raised in summary.sh; a 100k-character
        # numeric field is a valid reading, not a record the parser rejects.
        text = HEADER + "2024-01-01,ALPHA,%s.5\n" % ("1" * 100000)
        result = run_csv(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALPHA 1 ", result.stdout)
        self.assertEqual(total_of(result.stdout), 1)
        self.assertIn("SKIPPED 0\n", result.stdout)

    def test_req_002_non_ascii_station_ids_are_aggregated(self):
        text = (
            HEADER
            + "2024-01-01,日本,1.0\n"
            + "2024-01-02,日本,3.0\n"
            + "2024-01-03,ALPHA,2.0\n"
        )
        result = run_csv(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("日本 2 1.0 3.0 2.0\n", result.stdout)
        self.assertIn("ALPHA 1 2.0 2.0 2.0\n", result.stdout)
        self.assertEqual(total_of(result.stdout), 3)

    def test_req_005_an_undecodable_byte_does_not_abort_the_run(self):
        # A raw byte that is not valid UTF-8 must turn the affected field into a
        # replacement character, not crash the decode.  The file is written as
        # bytes so the test controls the exact encoding.
        path = write_bytes(
            b"date,station,temperature_c\n"
            b"2024-01-01,AL\xffPHA,1.0\n"
            b"2024-01-02,BRAVO,2.0\n"
        )
        try:
            result = subprocess.run(
                ["bash", SCRIPT, path],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
        finally:
            os.unlink(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("BRAVO 1 2.0 2.0 2.0\n", result.stdout)
        self.assertIn("AL\ufffdPHA 1 1.0 1.0 1.0\n", result.stdout)
        self.assertEqual(total_of(result.stdout), 2)

    def test_amb_003_negative_zero_normalises_to_zero(self):
        result = run_csv(HEADER + "2024-01-01,ALPHA,-0.0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "ALPHA 1 0.0 0.0 0.0\nSKIPPED 0\nTOTAL 1\n",
        )


class NonAsciiOrderingTests(unittest.TestCase):
    """REQ-007 / AMB-004: byte-wise ordering holds for non-ASCII ids too."""

    def test_amb_004_non_ascii_station_ids_are_ordered_byte_wise(self):
        text = (
            HEADER
            + "2024-01-01,日本,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,Ä,3.0\n"
            + "2024-01-04,zeta,4.0\n"
        )
        result = run_csv(text)
        names = [
            line.split(" ")[0]
            for line in station_lines(result.stdout)
        ]
        # Byte-wise UTF-8: 'A' (0x41) < 'z' (0x7A) < 'Ä' (0xC3 0x84) < '日'
        # (0xE6 0x97 0xA5).  This matches code-point order, but pins that the
        # sort is over the encoded bytes rather than a locale collation.
        self.assertEqual(names, ["ALPHA", "zeta", "Ä", "日本"])


if __name__ == "__main__":
    unittest.main()
