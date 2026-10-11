"""REQ-008 and REQ-009: offline operation and a year of readings."""

import os
import re
import time
import unittest

from helpers import HEADER, ROOT, SCRIPT, run_csv


class OfflineTests(unittest.TestCase):
    """REQ-008: the tool makes no network calls."""

    def test_source_imports_no_network_module(self):
        with open(SCRIPT, "r", encoding="utf-8") as handle:
            source = handle.read()
        for module in ("socket", "urllib", "http.client", "httplib", "requests", "ftplib"):
            self.assertNotRegex(source, r"(?m)^\s*(import|from)\s+%s" % re.escape(module))

    def test_output_is_unchanged_when_proxies_point_at_a_dead_endpoint(self):
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = run_csv(text, env=None)
        blocked = dict(os.environ)
        blocked.update(
            {
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "http_proxy": "http://127.0.0.1:9",
                "https_proxy": "http://127.0.0.1:9",
                "NO_PROXY": "",
            }
        )
        offline = run_csv(text, env=blocked)
        self.assertEqual(offline.returncode, 0)
        self.assertEqual(offline.stdout, baseline.stdout)

    def test_relative_parent_is_never_consulted_for_data(self):
        # The tool must read the file named by $1, not some ambient file.
        result = run_csv(HEADER + "2024-01-01,ALPHA,10.4\n")
        self.assertEqual(result.stdout, "ALPHA 1 10.4 10.4 10.4\nSKIPPED 0\nTOTAL 1\n")


class PerformanceTests(unittest.TestCase):
    """REQ-009: about 200,000 readings finish in a couple of seconds."""

    @staticmethod
    def _year_fixture(path, rows=200000):
        stations = ["STATION-%03d" % index for index in range(50)]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(HEADER)
            for index in range(rows):
                month = index % 12 + 1
                day = index % 28 + 1
                station = stations[index % len(stations)]
                value = -20 + (index % 600) / 10.0
                handle.write("2024-%02d-%02d,%s,%.1f\n" % (month, day, station, value))

    def test_two_hundred_thousand_rows_finish_quickly(self):
        import subprocess
        import tempfile

        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
        path = handle.name
        handle.close()
        try:
            self._year_fixture(path, rows=200000)
            started = time.perf_counter()
            result = subprocess.run(
                ["bash", SCRIPT, path],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            elapsed = time.perf_counter() - started
        finally:
            os.unlink(path)

        self.assertEqual(result.returncode, 0)
        lines = [line for line in result.stdout.splitlines() if line]
        self.assertEqual(sum(int(line.split(" ")[1]) for line in lines if not line.startswith(("SKIPPED ", "TOTAL "))), 200000)
        self.assertIn("TOTAL 200000\n", result.stdout)
        self.assertIn("SKIPPED 0\n", result.stdout)
        # A couple of seconds on a developer laptop; generous enough for a busy
        # CI runner while still failing a quadratic implementation.
        self.assertLess(elapsed, 20.0, "200k rows took %.2fs" % elapsed)
