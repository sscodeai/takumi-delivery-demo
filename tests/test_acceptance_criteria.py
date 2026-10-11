"""Acceptance-criterion traceability for the service requirement document.

Every acceptance criterion of ``docs/requirements/service-station-summary.yaml``
has a behavioural test here, one test per criterion or per confirmed ambiguity
(AMB-001..AMB-005).  The tests drive the delivered surface the way the document
declares it -- ``bash serve.sh <csv> <port>`` answering on
``http://127.0.0.1:<port>/summary`` -- and the pure aggregation functions at the
unit boundary where that is enough.  The declared relations (REL-001..REL-004)
and the differential (DIFF-001) are pinned as well.

The test names carry the requirement and ambiguity identifiers so a reader can
map a failure back to the clause it violates.
"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from helpers import HEADER  # noqa: E402 - path set above
from reference import reference_lines  # noqa: E402 - path set above
from test_service import SAMPLE, Service, declared_objects  # noqa: E402

import station_service  # noqa: E402 - path set above

DOCUMENT = os.path.join(ROOT, "docs", "requirements", "service-station-summary.yaml")
ONE_DECIMAL = re.compile(r"^-?[0-9]+\.[0-9]$")


def read_document():
    with open(DOCUMENT, "r", encoding="utf-8") as handle:
        return handle.read()


def station_objects(objects):
    return [obj for obj in objects if "station" in obj]


def objects_for(text):
    """Summarise ``text`` through the unit boundary and return JSON objects."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    try:
        handle.write(text)
        handle.close()
        body = station_service.summarise(handle.name).decode("utf-8")
    finally:
        os.unlink(handle.name)
    return [json.loads(line) for line in body.splitlines() if line.strip()]


class Req001JsonEndpointTests(unittest.TestCase):
    """REQ-001: expose the summary as a JSON endpoint."""

    def test_req001_started_service_answers_on_the_declared_url(self):
        # AC1: started by a declared command and answers on a declared URL.
        with Service(SAMPLE) as svc:
            status, headers, body = svc.fetch("/summary")
            self.assertTrue(svc.alive())
        self.assertEqual(status, 200)
        self.assertIn("json", headers.get("Content-Type", "").lower())
        self.assertIn('"total"', body)

    def test_req001_body_is_json_not_a_printed_text_table(self):
        # AC2: the response body is JSON, not a printed text table.
        with Service(SAMPLE) as svc:
            body = svc.body()
        lines = [line for line in body.splitlines() if line.strip()]
        self.assertTrue(lines)
        for line in lines:
            self.assertIsInstance(json.loads(line), dict)
            self.assertNotIn("'", line)
            self.assertNotIn("SKIPPED ", line)

    def test_req001_every_station_with_a_valid_reading_appears(self):
        # AC3: every station with at least one valid reading appears.
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,BRAVO,2.0\n"
            + "bad,BROKEN,3.0\n"
        )
        with Service(text) as svc:
            objects = svc.objects()
        names = [obj["station"] for obj in station_objects(objects)]
        self.assertEqual(names, ["ALPHA", "BRAVO"])
        self.assertNotIn("BROKEN", names)

    def test_req001_response_carries_the_overall_valid_reading_count(self):
        # AC4: the response carries the overall valid-reading count.
        with Service(SAMPLE) as svc:
            objects = svc.objects()
        totals = [obj["total"] for obj in objects if "total" in obj]
        self.assertEqual(totals, [5])


class Req002StartAndBoundTests(unittest.TestCase):
    """REQ-002: declare how the service starts and how one invocation is bounded."""

    def test_req002_declared_command_starts_a_long_running_service(self):
        # AC1: the deliverable declares how the service is started.  A
        # start-and-serve command runs until it is killed.
        document = read_document()
        self.assertIn('run: "bash serve.sh {csv} {port}"', document)
        with Service(SAMPLE) as svc:
            self.assertTrue(svc.alive())
        self.assertFalse(svc.alive())

    def test_req002_document_bounds_one_invocation(self):
        # AC2: a bound is declared so a command that never exits fails instead
        # of hanging the check.
        match = re.search(r"(?m)^\s*timeoutMs:\s*(\d+)\s*$", read_document())
        self.assertIsNotNone(match, "the deliverable declares no timeoutMs")
        self.assertGreater(int(match.group(1)), 0)

    def test_req002_document_has_no_build_or_tests_key(self):
        # AC3: the delivered project's tests are run from the workflow, so the
        # document declares no build or tests key.
        document = read_document()
        self.assertNotRegex(document, r"(?m)^\s*build:")
        self.assertNotRegex(document, r"(?m)^\s*tests:")


class Req003ParsingTests(unittest.TestCase):
    """REQ-003: parse the daily temperature CSV."""

    def test_req003_header_line_is_consumed(self):
        # AC1: the header line is consumed and never a reading.
        objects = objects_for(HEADER + "2024-01-01,ALPHA,1.0\n")
        self.assertEqual(station_objects(objects), [
            {"station": "ALPHA", "count": 1, "min": 1.0, "max": 1.0, "mean": 1.0}
        ])
        self.assertEqual([obj for obj in objects if "total" in obj], [{"total": 1}])

    def test_req003_each_well_formed_row_is_one_reading(self):
        # AC2: each well-formed row counts as exactly one reading.
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BRAVO,3.0\n"
        )
        objects = objects_for(text)
        counts = {obj["station"]: obj["count"] for obj in station_objects(objects)}
        self.assertEqual(counts, {"ALPHA": 2, "BRAVO": 1})


class Req004RoundingTests(unittest.TestCase):
    """REQ-004: round to one decimal place, half away from zero."""

    def test_req004_min_max_mean_carry_exactly_one_decimal(self):
        text = HEADER + "2024-01-01,ALPHA,1\n" + "2024-01-02,ALPHA,2.5\n"
        with Service(text) as svc:
            _status, _headers, body = svc.fetch()
        fields = re.findall(r'"(?:min|max|mean)":([^,}]+)', body)
        self.assertEqual(fields, ["1.0", "2.5", "1.8"])
        for token in fields:
            self.assertRegex(token, ONE_DECIMAL)


class Req005MalformedTests(unittest.TestCase):
    """REQ-005: account for malformed rows without crashing."""

    def test_req005_malformed_fixture_completes_and_service_stays_up(self):
        # AC1: a fixture with malformed rows is summarised to completion and the
        # service stays up.
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-01,ALPHA\n"
            + "bad-date,ALPHA,2.0\n"
            + "2024-01-01,ALPHA,abc\n"
        )
        with Service(text) as svc:
            first = svc.objects()
            self.assertTrue(svc.alive())
            second = svc.objects()
            self.assertTrue(svc.alive())
        self.assertEqual(first, second)

    def test_req005_malformed_rows_never_change_a_count_min_max_or_mean(self):
        # AC2: malformed rows never change a count, min, max or mean.
        valid = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,3.0\n"
        dirty = (
            valid
            + "2024-01-01,ALPHA\n"
            + "bad,ALPHA,9.0\n"
            + "2024-01-01,,7.0\n"
            + "2024-01-01,ALPHA,xx\n"
        )
        clean_objects = objects_for(valid)
        dirty_objects = objects_for(dirty)
        self.assertEqual(
            station_objects(clean_objects), station_objects(dirty_objects)
        )
        self.assertEqual(
            [obj for obj in dirty_objects if "skipped" in obj], [{"skipped": 4}]
        )


class Req006OrderIndependenceTests(unittest.TestCase):
    """REQ-006: row-order-independent summary."""

    def test_req006_permuting_data_rows_yields_the_same_summary(self):
        import random

        rows = [
            "2024-01-01,ALPHA,1.2",
            "2024-01-01,BRAVO,-2.5",
            "2024-01-02,ALPHA,3.4",
            "2024-01-02,CHARLIE,0.05",
            "2024-01-03,BRAVO,7.7",
            "2024-01-01,ALPHA",
            "bad,BRAVO,1.0",
        ]
        baseline = objects_for(HEADER + "\n".join(rows) + "\n")
        for seed in range(5):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(objects_for(HEADER + "\n".join(shuffled) + "\n"), baseline)


class Req007OfflineTests(unittest.TestCase):
    """REQ-007: offline operation."""

    def test_req007_delivered_source_imports_no_outbound_client(self):
        for name in ("station_service.py", "serve.sh"):
            with open(os.path.join(ROOT, name), "r", encoding="utf-8") as handle:
                source = handle.read()
            for module in ("http.client", "urllib.request", "requests", "ftplib"):
                self.assertNotRegex(
                    source, r"(?m)^\s*(import|from)\s+%s\b" % re.escape(module)
                )

    def test_req007_summary_is_unchanged_with_outbound_networking_blocked(self):
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
        text = HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n"
        baseline = objects_for(text)
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        try:
            handle.write(text)
            handle.close()
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                probe.bind(("127.0.0.1", 0))
                chosen = probe.getsockname()[1]
            finally:
                probe.close()
            proc = subprocess.Popen(
                ["bash", os.path.join(ROOT, "serve.sh"), handle.name, str(chosen)],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=blocked,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 20
                body = None
                while time.monotonic() < deadline:
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:%d/summary" % chosen, timeout=2
                        ) as response:
                            body = response.read().decode("utf-8")
                            break
                    except OSError:
                        time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=10)
                proc.stderr.close()
        finally:
            os.unlink(handle.name)
        self.assertIsNotNone(body, "the service did not answer while offline")
        self.assertEqual(declared_objects(body), baseline)


class AmbiguityTests(unittest.TestCase):
    """Every AMB-nnn entry's chosen behaviour, checked on the delivered surface."""

    def test_amb001_malformed_rows_are_skipped_excluded_and_counted(self):
        # skip-count: skipped, excluded from every aggregate, counted.
        text = HEADER + "2024-01-01,ALPHA,1.0\nnot-a-date,ALPHA,99.0\n"
        objects = objects_for(text)
        self.assertEqual(
            station_objects(objects),
            [{"station": "ALPHA", "count": 1, "min": 1.0, "max": 1.0, "mean": 1.0}],
        )
        self.assertEqual([obj for obj in objects if "skipped" in obj], [{"skipped": 1}])

    def test_amb002_repeated_date_station_rows_merge_as_separate_readings(self):
        # merge: each occurrence remains a separate valid reading.
        text = (
            HEADER
            + "2024-01-01,ALPHA,5.0\n"
            + "2024-01-01,ALPHA,-3.0\n"
            + "2024-01-01,ALPHA,1.0\n"
        )
        objects = objects_for(text)
        self.assertEqual(
            station_objects(objects),
            [{"station": "ALPHA", "count": 3, "min": -3.0, "max": 5.0, "mean": 1.0}],
        )

    def test_amb003_ties_round_half_away_from_zero(self):
        # half-up: round half away from zero.
        for raw, want in (("1.25", 1.3), ("-1.25", -1.3), ("0.05", 0.1), ("-0.05", -0.1)):
            with self.subTest(raw=raw):
                objects = objects_for(HEADER + "2024-01-01,ALPHA,%s\n" % raw)
                station = station_objects(objects)[0]
                self.assertEqual(station["min"], want)
                self.assertEqual(station["max"], want)
                self.assertEqual(station["mean"], want)

    def test_amb004_stations_are_ordered_by_ascending_byte_wise_id(self):
        # ascending station id, byte-wise lexicographic.
        text = (
            HEADER
            + "2024-01-01,zeta,1.0\n"
            + "2024-01-02,\u00e9psilon,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
            + "2024-01-04,alpha,4.0\n"
        )
        objects = objects_for(text)
        names = [obj["station"] for obj in station_objects(objects)]
        self.assertEqual(names, ["ALPHA", "alpha", "zeta", "\u00e9psilon"])

    def test_amb005_total_counts_valid_readings_only(self):
        # valid readings only: the sum of the per-station counts.
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BETA,3.0\n"
            + "not-a-date,GAMMA,4.0\n"
        )
        objects = objects_for(text)
        counts = [obj["count"] for obj in station_objects(objects)]
        total = [obj["total"] for obj in objects if "total" in obj][0]
        skipped = [obj["skipped"] for obj in objects if "skipped" in obj][0]
        self.assertEqual(sum(counts), total)
        self.assertEqual(total, 3)
        self.assertEqual(skipped, 1)


class RelationAndDifferentialTests(unittest.TestCase):
    """REL-001..REL-004 and DIFF-001: the declared invariants hold."""

    def test_rel001_row_order_invariance(self):
        rows = [
            "2024-01-01,ALPHA,1.2",
            "2024-01-01,BRAVO,-2.5",
            "2024-01-02,ALPHA,3.4",
        ]
        forward = objects_for(HEADER + "\n".join(rows) + "\n")
        backward = objects_for(HEADER + "\n".join(reversed(rows)) + "\n")
        self.assertEqual(forward, backward)

    def test_rel002_additivity_per_station_counts_sum_to_total(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BETA,3.0\n"
            + "2024-01-04,GAMMA,4.0\n"
        )
        objects = objects_for(text)
        counts = [obj["count"] for obj in station_objects(objects)]
        total = [obj["total"] for obj in objects if "total" in obj][0]
        self.assertEqual(sum(counts), total)

    def test_rel003_duplicate_resolution_merges_occurrences(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-01,ALPHA,2.0\n"
        objects = objects_for(text)
        self.assertEqual(station_objects(objects)[0]["count"], 2)

    def test_rel004_malformed_row_accounting(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-01,ALPHA\nbad,x,1.0\n"
        objects = objects_for(text)
        self.assertEqual([obj for obj in objects if "skipped" in obj], [{"skipped": 2}])
        self.assertEqual(station_objects(objects)[0]["count"], 1)

    def test_diff001_service_json_agrees_with_an_independent_computation(self):
        cases = [
            HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n",
            HEADER + "2024-01-01,ALPHA,1.25\n2024-01-02,ALPHA,2.35\n",
            HEADER + "2024-01-01,ALPHA,-1.25\n2024-01-02,BRAVO,0.05\n",
        ]
        for text in cases:
            with self.subTest(rows=text.splitlines()[:3]):
                expected = reference_lines(text)
                expected_stations = []
                for line in expected:
                    if line.startswith(("SKIPPED ", "TOTAL ")):
                        continue
                    name, count, minimum, maximum, mean = line.split(" ")
                    expected_stations.append((name, int(count), minimum, maximum, mean))
                objects = objects_for(text)
                actual = [
                    (
                        obj["station"],
                        obj["count"],
                        repr(obj["min"]),
                        repr(obj["max"]),
                        repr(obj["mean"]),
                    )
                    for obj in station_objects(objects)
                ]
                self.assertEqual(actual, expected_stations)


class SmokeGateTests(unittest.TestCase):
    """The smoke gate must be able to run this suite and see it fail."""

    def test_run_tests_sh_exits_zero_when_the_suite_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(ROOT, "run-tests.sh"), os.path.join(tmp, "run-tests.sh"))
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            with open(
                os.path.join(tests_dir, "test_pass.py"), "w", encoding="utf-8"
            ) as handle:
                handle.write(
                    "import unittest\n\n"
                    "class Pass(unittest.TestCase):\n"
                    "    def test_pass(self):\n"
                    "        self.assertTrue(True)\n"
                )
            result = subprocess.run(
                ["bash", os.path.join(tmp, "run-tests.sh")],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_run_tests_sh_exits_nonzero_when_a_test_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(ROOT, "run-tests.sh"), os.path.join(tmp, "run-tests.sh"))
            tests_dir = os.path.join(tmp, "tests")
            os.makedirs(tests_dir)
            with open(
                os.path.join(tests_dir, "test_fail.py"), "w", encoding="utf-8"
            ) as handle:
                handle.write(
                    "import unittest\n\n"
                    "class Fail(unittest.TestCase):\n"
                    "    def test_fail(self):\n"
                    "        self.assertEqual(1, 2)\n"
                )
            result = subprocess.run(
                ["bash", os.path.join(tmp, "run-tests.sh")],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
