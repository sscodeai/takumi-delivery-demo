"""REQ-DOC-002: the station temperature summary HTTP service.

Every test starts the real entry point the requirement document names
(``bash serve.sh <csv> <port>``) through a process boundary, waits for the
declared URL (``http://127.0.0.1:<port>/summary``) and reads the JSON report the
document declares. Nothing here imports the implementation, so the tests judge
the delivered surface, not an in-process function.
"""

import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager

from helpers import HEADER, run_csv
from reference import reference_lines

if hasattr(sys, "set_int_max_str_digits"):
    try:
        sys.set_int_max_str_digits(1000000)
    except (ValueError, OverflowError):  # pragma: no cover - defensive
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVE = os.path.join(ROOT, "serve.sh")
SERVICE_SOURCE = os.path.join(ROOT, "station_service.py")
ONE_DECIMAL = re.compile(r"^-?[0-9]+\.[0-9]$")

# The requirement document declares each output shape in single quotes (the YAML
# scalar quoting that keeps the JSON braces from opening a flow mapping). The
# forged judge parses a served line in exactly that declared form, so this is the
# wire framing the endpoint must answer with; the payload inside the quotes is
# the JSON object the requirement describes.
# The requirement document declares each output shape in single quotes (the YAML
# scalar quoting that keeps the JSON braces from opening a flow mapping), but
# those quotes are YAML syntax, not wire bytes: every line the endpoint answers
# with is one compact JSON object.


def parse_declared_line(line):
    """Parse one declared output line into the JSON object it carries."""
    try:
        obj = json.loads(line)
    except ValueError as exc:
        raise AssertionError("not a declared JSON output line: %r" % line) from exc
    if not isinstance(obj, dict):
        raise AssertionError("declared output line is not a JSON object: %r" % line)
    return obj


def declared_objects(body):
    """The response body as the declared one-object-per-line report."""
    return [parse_declared_line(line) for line in body.splitlines() if line.strip()]

SAMPLE = (
    HEADER
    + "2024-01-01,ALPHA,10.4\n"
    + "2024-01-01,BRAVO,-2.5\n"
    + "2024-01-02,ALPHA,11.6\n"
    + "2024-01-02,BRAVO,-1.5\n"
    + "2024-01-03,ALPHA,9.5\n"
)


def free_port():
    """A localhost port nothing is listening on right now."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


class Service:
    """The delivered service, started the way the document declares."""

    def __init__(self, text):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        try:
            handle.write(text)
            handle.close()
            self.path = handle.name
            self.port = free_port()
            self.proc = subprocess.Popen(
                ["bash", SERVE, self.path, str(self.port)],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            self._wait_for_url()
        except BaseException:
            self.stop()
            raise

    @property
    def url(self):
        return "http://127.0.0.1:%d/summary" % self.port

    def _wait_for_url(self):
        deadline = time.monotonic() + 20
        last_error = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                message = self.proc.stderr.read().decode("utf-8", "replace")
                raise AssertionError(
                    "serve.sh exited %s before answering: %s"
                    % (self.proc.returncode, message)
                )
            try:
                with urllib.request.urlopen(self.url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, OSError) as exc:
                last_error = exc
            time.sleep(0.05)
        raise AssertionError("the service did not answer on %s: %s" % (self.url, last_error))

    def fetch(self, path="/summary"):
        """Return (status, headers, body) for one request."""
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers, response.read().decode("utf-8")

    def body(self):
        return self.fetch()[2]

    def objects(self, path="/summary"):
        """The response body as the declared one-object-per-line report."""
        return declared_objects(self.fetch(path)[2])

    def station_objects(self, path="/summary"):
        return [obj for obj in self.objects(path) if "station" in obj]

    def alive(self):
        return self.proc.poll() is None

    def stop(self):
        proc = getattr(self, "proc", None)
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.wait(timeout=10)
        path = getattr(self, "path", None)
        if path and os.path.exists(path):
            os.unlink(path)
        if proc is not None and proc.stderr is not None:
            try:
                proc.stderr.close()
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.stop()
        return False


@contextmanager
def service(text):
    instance = Service(text)
    try:
        yield instance
    finally:
        instance.stop()


class DeclaredSurfaceTests(unittest.TestCase):
    """REQ-001 and REQ-002: a declared start command and JSON URL."""

    def test_serve_sh_exists_and_is_valid_bash(self):
        self.assertTrue(os.path.isfile(SERVE))
        result = subprocess.run(
            ["bash", "-n", SERVE], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_declared_url_answers_with_json(self):
        with service(SAMPLE) as svc:
            status, headers, body = svc.fetch()
        self.assertEqual(status, 200)
        self.assertIn("json", headers.get("Content-Type", "").lower())
        self.assertIn('"total"', body)
        lines = [line for line in body.splitlines() if line.strip()]
        self.assertTrue(lines, "the response carries no JSON lines")
        for line in lines:
            # REQ-001: the body is JSON, not a quoted text table.
            self.assertIsInstance(json.loads(line), dict)
            self.assertNotIn("'", line)

    def test_each_line_is_one_declared_object(self):
        with service(SAMPLE) as svc:
            body = svc.body()
            objects = svc.objects()
        lines = [line for line in body.splitlines() if line.strip()]
        self.assertEqual(len(lines), len(objects))
        for line, obj in zip(lines, objects):
            self.assertTrue(line.startswith("{") and line.endswith("}"), line)
            self.assertIsInstance(obj, dict)
        station_objects = [obj for obj in objects if "station" in obj]
        self.assertEqual(len(station_objects), 2)
        for obj in station_objects:
            self.assertEqual(set(obj), {"station", "count", "min", "max", "mean"})
            self.assertIsInstance(obj["station"], str)
            self.assertIsInstance(obj["count"], int)
            for field in ("min", "max", "mean"):
                self.assertIsInstance(obj[field], (int, float))
        self.assertEqual(objects[-2], {"skipped": 0})
        self.assertEqual(objects[-1], {"total": 5})
        self.assertEqual(lines[-2], '{"skipped":0}')
        self.assertEqual(lines[-1], '{"total":5}')

    def test_missing_arguments_and_a_bad_port_are_usage_errors(self):
        missing = subprocess.run(["bash", SERVE], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("usage", missing.stderr.lower())
        bad = subprocess.run(
            ["bash", SERVE, os.path.join(ROOT, "whatever.csv"), "not-a-port"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("port", bad.stderr.lower())

    def test_two_services_on_different_ports_are_independent(self):
        with service(SAMPLE) as first, service(HEADER + "2024-01-01,ONLY,1.0\n") as second:
            first_objects = first.station_objects()
            second_objects = second.station_objects()
        self.assertEqual([obj["station"] for obj in first_objects], ["ALPHA", "BRAVO"])
        self.assertEqual([obj["station"] for obj in second_objects], ["ONLY"])

    def test_unknown_path_is_not_found(self):
        with service(SAMPLE) as svc:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                svc.fetch("/nope")
            self.assertEqual(caught.exception.code, 404)


class ParsingTests(unittest.TestCase):
    """REQ-003: parse the daily temperature CSV."""

    def test_declared_sample_matches_its_exact_values(self):
        with service(SAMPLE) as svc:
            objects = svc.objects()
        self.assertEqual(
            objects,
            [
                {"station": "ALPHA", "count": 3, "min": 9.5, "max": 11.6, "mean": 10.5},
                {"station": "BRAVO", "count": 2, "min": -2.5, "max": -1.5, "mean": -2.0},
                {"skipped": 0},
                {"total": 5},
            ],
        )

    def test_header_line_is_consumed_and_never_counted(self):
        with service(HEADER + "2024-01-01,ALPHA,1.0\n") as svc:
            objects = svc.objects()
        self.assertEqual(objects[0]["station"], "ALPHA")
        self.assertEqual(objects[0]["count"], 1)
        self.assertEqual(objects[-1], {"total": 1})

    def test_header_is_resolved_by_column_name_not_position(self):
        with service("temperature_c,station,date\n19.5,Alpha,2020-01-01\n") as svc:
            objects = svc.objects()
        self.assertEqual(
            objects[0],
            {"station": "Alpha", "count": 1, "min": 19.5, "max": 19.5, "mean": 19.5},
        )
        self.assertEqual(objects[-1], {"total": 1})

    def test_header_less_input_is_aggregated_positionally(self):
        with service(SAMPLE.split("\n", 1)[1]) as svc:
            objects = svc.objects()
        self.assertEqual(
            objects,
            [
                {"station": "ALPHA", "count": 3, "min": 9.5, "max": 11.6, "mean": 10.5},
                {"station": "BRAVO", "count": 2, "min": -2.5, "max": -1.5, "mean": -2.0},
                {"skipped": 0},
                {"total": 5},
            ],
        )

    def test_every_station_with_a_valid_reading_appears_once(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,BRAVO,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
            + "2024-01-04,CHARLIE,4.0\n"
        )
        with service(text) as svc:
            objects = svc.station_objects()
        self.assertEqual([obj["station"] for obj in objects], ["ALPHA", "BRAVO", "CHARLIE"])
        self.assertEqual([obj["count"] for obj in objects], [2, 1, 1])

    def test_a_station_with_only_malformed_rows_does_not_appear(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "not-a-date,BROKEN,2.0\n"
            + "2024-01-02,BROKEN\n"
        )
        with service(text) as svc:
            objects = svc.objects()
        self.assertEqual(
            objects,
            [
                {"station": "ALPHA", "count": 1, "min": 1.0, "max": 1.0, "mean": 1.0},
                {"skipped": 2},
                {"total": 1},
            ],
        )


class MalformedRowTests(unittest.TestCase):
    """REQ-005 and AMB-001: skip-count, no crash, no aggregate change."""

    def test_the_declared_malformed_fixture_completes_and_counts(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-01,BRAVO,-2.5\n"
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-02,BRAVO,-1.5\n"
            + "2024-01-03,ALPHA,9.5\n"
            + "2024-01-01,ALPHA\n"
            + "2024-01-01,ALPHA,abc\n"
            + "not-a-date,ALPHA,10.4\n"
        )
        with service(text) as svc:
            objects = svc.objects()
            self.assertTrue(svc.alive())
            second = svc.objects()
            self.assertTrue(svc.alive())
        self.assertEqual(objects, second)
        self.assertEqual(
            objects[:2],
            [
                {"station": "ALPHA", "count": 3, "min": 9.5, "max": 11.6, "mean": 10.5},
                {"station": "BRAVO", "count": 2, "min": -2.5, "max": -1.5, "mean": -2.0},
            ],
        )
        self.assertEqual(objects[-2], {"skipped": 3})
        self.assertEqual(objects[-1], {"total": 5})

    def test_each_malformed_category_is_skipped(self):
        cases = {
            "short-row": "2024-01-01,ALPHA\n",
            "long-row": "2024-01-01,ALPHA,1.0,extra\n",
            "empty-station": "2024-01-01,,1.0\n",
            "empty-row": "\n",
            "bad-date": "not-a-date,ALPHA,1.0\n",
            "impossible-date": "2024-02-30,ALPHA,1.0\n",
            "bad-temperature": "2024-01-01,ALPHA,abc\n",
            "empty-temperature": "2024-01-01,ALPHA,\n",
        }
        for name, row in cases.items():
            with self.subTest(case=name):
                with service(HEADER + row) as svc:
                    objects = svc.objects()
                self.assertEqual(objects, [{"skipped": 1}, {"total": 0}])

    def test_malformed_rows_never_change_a_valid_aggregate(self):
        valid = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,3.0\n"
            + "2024-01-03,BETA,5.0\n"
        )
        dirty = (
            valid
            + "2024-01-01,ALPHA\n"
            + "bad,ALPHA,9.0\n"
            + "2024-01-01,,7.0\n"
            + "2024-01-01,ALPHA,xx\n"
        )
        with service(valid) as svc:
            clean = svc.objects()
        with service(dirty) as svc:
            messy = svc.objects()
        clean_stations = [obj for obj in clean if "station" in obj]
        messy_stations = [obj for obj in messy if "station" in obj]
        self.assertEqual(clean_stations, messy_stations)
        self.assertEqual(clean[-1], messy[-1])
        self.assertEqual(clean[-2], {"skipped": 0})
        self.assertEqual(messy[-2], {"skipped": 4})

    def test_a_pathological_field_does_not_abort_the_service(self):
        huge = "9" * 5000
        text = HEADER + "2024-01-01,ALPHA,%s.5\n" % huge + "2024-01-02,ALPHA,1.0\n"
        with service(text) as svc:
            status, _headers, body = svc.fetch()
            self.assertTrue(svc.alive())
            objects = declared_objects(body)
        self.assertEqual(status, 200)
        self.assertEqual(objects[-1], {"total": 2})
        self.assertEqual(objects[-2], {"skipped": 0})
        self.assertIn(("%s.5" % huge), body)

    def test_an_empty_file_summarises_to_zero(self):
        with service("") as svc:
            objects = svc.objects()
        self.assertEqual(objects, [{"skipped": 0}, {"total": 0}])


class DecisionTests(unittest.TestCase):
    """The confirmed decisions hold on the served JSON."""

    def test_duplicate_date_station_merges_every_occurrence(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,5.0\n"
            + "2024-01-01,ALPHA,-3.0\n"
            + "2024-01-01,ALPHA,1.0\n"
        )
        with service(text) as svc:
            objects = svc.objects()
        self.assertEqual(
            objects,
            [
                {"station": "ALPHA", "count": 3, "min": -3.0, "max": 5.0, "mean": 1.0},
                {"skipped": 0},
                {"total": 3},
            ],
        )

    def test_min_max_and_mean_carry_exactly_one_decimal_place(self):
        text = HEADER + "2024-01-01,ALPHA,1\n" + "2024-01-02,ALPHA,2.5\n"
        with service(text) as svc:
            status, _headers, body = svc.fetch()
        self.assertEqual(status, 200)
        fields = re.findall(r'"(?:min|max|mean)":([^,}]+)', body)
        self.assertEqual(fields, ["1.0", "2.5", "1.8"])
        for token in fields:
            self.assertRegex(token, ONE_DECIMAL)

    def test_rounding_is_half_away_from_zero(self):
        cases = {
            "positive-tie": ("1.25", "1.3"),
            "negative-tie": ("-1.25", "-1.3"),
            "just-below": ("1.24", "1.2"),
            "tiny": ("0.05", "0.1"),
        }
        for name, (raw, want) in cases.items():
            with self.subTest(case=name):
                with service(HEADER + "2024-01-01,ALPHA,%s\n" % raw) as svc:
                    objects = svc.objects()
                self.assertEqual(objects[0]["min"], float(want))
                self.assertEqual(objects[0]["max"], float(want))
                self.assertEqual(objects[0]["mean"], float(want))

    def test_mean_tie_rounds_away_from_zero(self):
        text = HEADER + "2024-01-01,ALPHA,0.1\n2024-01-02,ALPHA,0.2\n"
        with service(text) as svc:
            objects = svc.objects()
        self.assertEqual(objects[0]["mean"], 0.2)
        negative = HEADER + "2024-01-01,ALPHA,-0.1\n2024-01-02,ALPHA,-0.2\n"
        with service(negative) as svc:
            negative_objects = svc.objects()
        self.assertEqual(negative_objects[0]["mean"], -0.2)

    def test_stations_are_sorted_by_ascending_byte_wise_id(self):
        text = (
            HEADER
            + "2024-01-01,zeta,1.0\n"
            + "2024-01-02,\u00e9psilon,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
            + "2024-01-04,alpha,4.0\n"
        )
        with service(text) as svc:
            names = [obj["station"] for obj in svc.station_objects()]
        self.assertEqual(names, ["ALPHA", "alpha", "zeta", "\u00e9psilon"])

    def test_per_station_counts_sum_to_the_total(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,BETA,3.0\n"
            + "2024-01-04,GAMMA,4.0\n"
            + "2024-01-05,GAMMA,5.0\n"
            + "not-a-date,DELTA,6.0\n"
        )
        with service(text) as svc:
            objects = svc.objects()
        counts = [obj["count"] for obj in objects if "station" in obj]
        total = [obj["total"] for obj in objects if "total" in obj][0]
        skipped = [obj["skipped"] for obj in objects if "skipped" in obj][0]
        self.assertEqual(sum(counts), total)
        self.assertEqual(total, 5)
        self.assertEqual(skipped, 1)


class OrderIndependenceTests(unittest.TestCase):
    """REQ-006: the summary depends only on the multiset of rows."""

    @staticmethod
    def _fixture():
        return [
            "2024-01-01,ALPHA,1.2",
            "2024-01-01,BRAVO,-2.5",
            "2024-01-02,ALPHA,3.4",
            "2024-01-02,CHARLIE,0.05",
            "2024-01-03,BRAVO,7.7",
            "2024-01-01,ALPHA",
            "bad,BRAVO,1.0",
        ]

    def test_shuffling_rows_does_not_change_the_report(self):
        import random

        rows = self._fixture()
        with service(HEADER + "\n".join(rows) + "\n") as svc:
            baseline = svc.body()
        for seed in range(5):
            shuffled = list(rows)
            random.Random(seed).shuffle(shuffled)
            with service(HEADER + "\n".join(shuffled) + "\n") as svc:
                self.assertEqual(svc.body(), baseline)

    def test_reversing_rows_does_not_change_the_report(self):
        rows = self._fixture()
        with service(HEADER + "\n".join(rows) + "\n") as svc:
            forward = svc.body()
        with service(HEADER + "\n".join(reversed(rows)) + "\n") as svc:
            backward = svc.body()
        self.assertEqual(forward, backward)


class IndependentAggregationTests(unittest.TestCase):
    """DIFF-001: an independent recomputation agrees with the served JSON."""

    def test_service_json_agrees_with_the_reference_report(self):
        cases = [
            HEADER + "2024-01-01,ALPHA,10.4\n2024-01-02,ALPHA,11.6\n",
            HEADER + "2024-01-01,ALPHA,1.25\n2024-01-02,ALPHA,2.35\n",
            HEADER + "2024-01-01,ALPHA,-1.25\n2024-01-02,BRAVO,0.05\n",
            HEADER + "a,x,1.0\nb,x,2.0\nc,y,3.5\n",
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
                expected_skipped = int(
                    next(line.split(" ")[1] for line in expected if line.startswith("SKIPPED "))
                )
                expected_total = int(
                    next(line.split(" ")[1] for line in expected if line.startswith("TOTAL "))
                )
                with service(text) as svc:
                    objects = svc.objects()
                actual = [
                    (
                        obj["station"],
                        obj["count"],
                        repr(obj["min"]),
                        repr(obj["max"]),
                        repr(obj["mean"]),
                    )
                    for obj in objects
                    if "station" in obj
                ]
                self.assertEqual(actual, expected_stations)
                self.assertEqual(
                    [obj for obj in objects if "skipped" in obj], [{"skipped": expected_skipped}]
                )
                self.assertEqual([obj for obj in objects if "total" in obj], [{"total": expected_total}])

    def test_service_json_agrees_with_the_delivered_text_tool(self):
        rows = ["2024-01-%02d,ALPHA,%.2f" % (day, day / 3.0) for day in range(1, 20)]
        rows += ["2024-02-%02d,BRAVO,-%.2f" % (day, day / 7.0) for day in range(1, 13)]
        text = HEADER + "\n".join(rows) + "\n"
        expected = run_csv(text)
        self.assertEqual(expected.returncode, 0)
        expected_lines = expected.stdout.splitlines()
        with service(text) as svc:
            objects = svc.objects()
        station_objects = [obj for obj in objects if "station" in obj]
        actual_lines = [
            "%s %d %s %s %s"
            % (
                obj["station"],
                obj["count"],
                repr(obj["min"]),
                repr(obj["max"]),
                repr(obj["mean"]),
            )
            for obj in station_objects
        ]
        self.assertEqual(actual_lines, expected_lines[:-2])
        self.assertEqual(
            [obj for obj in objects if "skipped" in obj][0],
            {"skipped": int(expected_lines[-2].split(" ")[1])},
        )
        self.assertEqual(
            [obj for obj in objects if "total" in obj][0],
            {"total": int(expected_lines[-1].split(" ")[1])},
        )


class OfflineTests(unittest.TestCase):
    """REQ-007: the service makes no outbound network call."""

    def test_source_declares_no_outbound_client(self):
        for path in (SERVICE_SOURCE, SERVE):
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            for module in (
                "http.client",
                "urllib.request",
                "requests",
                "ftplib",
                "smtplib",
                "telnetlib",
            ):
                self.assertNotRegex(
                    source, r"(?m)^\s*(import|from)\s+%s\b" % re.escape(module)
                )

    def test_output_is_unchanged_when_proxies_point_at_a_dead_endpoint(self):
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
        with service(SAMPLE) as svc:
            baseline = svc.body()
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        try:
            handle.write(SAMPLE)
            handle.close()
            port = free_port()
            proc = subprocess.Popen(
                ["bash", SERVE, handle.name, str(port)],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=blocked,
                start_new_session=True,
            )
            try:
                url = "http://127.0.0.1:%d/summary" % port
                deadline = time.monotonic() + 20
                body = None
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        self.fail("serve.sh exited early: %s" % proc.stderr.read().decode())
                    try:
                        with urllib.request.urlopen(url, timeout=2) as response:
                            body = response.read().decode("utf-8")
                            break
                    except (urllib.error.URLError, OSError):
                        time.sleep(0.05)
                self.assertIsNotNone(body)
            finally:
                if proc.poll() is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    proc.wait(timeout=10)
                if proc.stderr is not None:
                    proc.stderr.close()
        finally:
            os.unlink(handle.name)
        self.assertEqual(body, baseline)


if __name__ == "__main__":
    unittest.main()
