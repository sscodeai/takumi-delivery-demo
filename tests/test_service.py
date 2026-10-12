"""REQ-DOC-002: the station temperature summary HTTP service.

Every test starts the real entry point the requirement document names
(``bash serve.sh <csv> <port>``) through a process boundary, waits for the
declared URL and reads the JSON report.  Nothing here imports the
implementation, so the tests judge the delivered surface rather than an
in-process function.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from helpers import HEADER
from reference import reference_lines
from service_harness import ROOT, SERVE, running_service

if hasattr(sys, "set_int_max_str_digits"):
    try:
        sys.set_int_max_str_digits(1000000)
    except (ValueError, OverflowError):  # pragma: no cover - defensive
        pass

SAMPLE = (
    HEADER
    + "2024-01-01,ALPHA,10.4\n"
    + "2024-01-01,BRAVO,-2.5\n"
    + "2024-01-02,ALPHA,11.6\n"
    + "2024-01-02,BRAVO,-1.5\n"
    + "2024-01-03,ALPHA,9.5\n"
)


def expected_stations(text):
    """The reference implementation's station objects, keyed by name."""
    stations = {}
    for line in reference_lines(text):
        parts = line.split(" ")
        if parts[0] in ("SKIPPED", "TOTAL"):
            continue
        stations[parts[0]] = {
            "station": parts[0],
            "count": int(parts[1]),
            "min": parts[2],
            "max": parts[3],
            "mean": parts[4],
        }
    return stations


def expected_skipped(text):
    return int(next(line for line in reference_lines(text) if line.startswith("SKIPPED ")).split(" ")[1])


def expected_total(text):
    return int(next(line for line in reference_lines(text) if line.startswith("TOTAL ")).split(" ")[1])


def write_csv(text):
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    handle.write(text)
    handle.close()
    return handle.name


class SummaryEndpointTests(unittest.TestCase):
    """REQ-001/REQ-003/REQ-004: the endpoint, its JSON shape and its aggregates."""

    def test_sample_answers_200_with_the_declared_json_objects(self):
        with running_service(SAMPLE) as service:
            self.assertEqual(service.request_status(), 200)
            objects, skipped, total = service.report()

            expected = expected_stations(SAMPLE)
            self.assertEqual([obj["station"] for obj in objects], list(expected))
            for obj in objects:
                self.assertEqual(obj, expected[obj["station"]])
            self.assertEqual(skipped, expected_skipped(SAMPLE))
            self.assertEqual(total, expected_total(SAMPLE))

    def test_response_is_one_valid_json_document(self):
        with running_service(SAMPLE) as service:
            document = json.loads(service.body().decode("utf-8"))
            self.assertIsInstance(document, list)
            self.assertEqual(len(document), 4)
            self.assertEqual(document[-2], {"skipped": 0})
            self.assertEqual(document[-1], {"total": 5})

    def test_every_station_with_a_valid_reading_appears(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-01,CHARLIE,2.0\n"
        with running_service(text) as service:
            objects, _, total = service.report()
            self.assertEqual(sorted(obj["station"] for obj in objects), ["ALPHA", "CHARLIE"])
            self.assertEqual(total, 2)

    def test_overall_total_is_the_sum_of_the_per_station_counts(self):
        with running_service(SAMPLE + "2024-01-03,BRAVO,-3.5\n") as service:
            objects, _, total = service.report()
            self.assertEqual(total, sum(obj["count"] for obj in objects))
            self.assertEqual(total, expected_total(SAMPLE + "2024-01-03,BRAVO,-3.5\n"))

    def test_min_max_and_mean_carry_exactly_one_decimal_place(self):
        text = HEADER + "2024-01-01,ALPHA,1\n2024-01-02,ALPHA,2\n2024-01-03,ALPHA,3\n"
        with running_service(text) as service:
            objects, _, _ = service.report()
            self.assertEqual(objects[0]["min"], "1.0")
            self.assertEqual(objects[0]["max"], "3.0")
            self.assertEqual(objects[0]["mean"], "2.0")

    def test_stations_are_ordered_by_ascending_byte_wise_id(self):
        text = (
            HEADER
            + "2024-01-01,10,1.0\n"
            + "2024-01-01,2,1.0\n"
            + "2024-01-01,Z,1.0\n"
            + "2024-01-01,a,1.0\n"
            + "2024-01-01,A,1.0\n"
            + "2024-01-01,z,1.0\n"
        )
        with running_service(text) as service:
            objects, _, _ = service.report()
            got = [obj["station"] for obj in objects]
            self.assertEqual(got, ["10", "2", "A", "Z", "a", "z"])
            self.assertEqual(got, sorted(got, key=lambda name: name.encode("utf-8")))


class HeaderTests(unittest.TestCase):
    """REQ-003: the header line is consumed and is not a reading."""

    def test_header_only_input_reports_no_stations(self):
        with running_service(HEADER) as service:
            objects, skipped, total = service.report()
            self.assertEqual(objects, [])
            self.assertEqual(skipped, 0)
            self.assertEqual(total, 0)

    def test_a_data_row_that_looks_like_a_station_is_still_a_reading(self):
        text = HEADER + "2024-01-01,date,1.0\n"
        with running_service(text) as service:
            objects, _, total = service.report()
            self.assertEqual(total, 1)
            self.assertEqual(objects[0]["station"], "date")


class MalformedRowTests(unittest.TestCase):
    """REQ-005/AMB-001: malformed rows never crash, never aggregate, are counted."""

    def test_malformed_rows_are_excluded_and_counted(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,10.4\n"
            + "2024-01-01,BRAVO\n"          # wrong field count
            + "2024-01-02,ALPHA,abc\n"      # non-numeric temperature
            + "not-a-date,ALPHA,1.0\n"      # unparseable date
            + ",BRAVO,-2.5\n"               # empty station
            + "\n"                          # empty record
            + "2024-01-02,ALPHA,11.6\n"
            + "2024-01-03,BRAVO,-1.5\n"
        )
        with running_service(text) as service:
            objects, skipped, total = service.report()
            expected = expected_stations(text)
            self.assertEqual({obj["station"]: obj for obj in objects}, expected)
            self.assertEqual(skipped, 5)
            self.assertEqual(skipped, expected_skipped(text))
            self.assertEqual(total, expected_total(text))
            self.assertEqual(total, 3)
            # The service is still up after summarising malformed rows.
            self.assertEqual(service.request_status(), 200)

    def test_a_calendar_invalid_date_is_malformed(self):
        text = HEADER + "2024-02-30,ALPHA,1.0\n" + "2024-01-01,ALPHA,2.0\n"
        with running_service(text) as service:
            objects, skipped, total = service.report()
            self.assertEqual(total, 1)
            self.assertEqual(skipped, 1)
            self.assertEqual(objects[0]["station"], "ALPHA")

    def test_a_trailing_fragment_after_the_date_is_malformed(self):
        # The previous step's fix at the HTTP boundary: a calendar-valid prefix
        # followed by arbitrary text used to be counted as a reading.  Through
        # the real service it must be skipped (AMB-001) and never aggregated.
        text = (
            HEADER
            + "2024-01-01Tbogus,ALPHA,1.0\n"
            + "2024-01-01 x,ALPHA,1.0\n"
            + "2024-01-01T25:00:00,ALPHA,1.0\n"
            + "2024-01-01T08:30:00,ALPHA,2.0\n"
        )
        with running_service(text) as service:
            objects, skipped, total = service.report()
            self.assertEqual(objects[0]["station"], "ALPHA")
            self.assertEqual(objects[0]["count"], 1)
            self.assertEqual(objects[0]["min"], "2.0")
            self.assertEqual(objects[0]["max"], "2.0")
            self.assertEqual(objects[0]["mean"], "2.0")
            self.assertEqual(skipped, 3)
            self.assertEqual(total, 1)
            self.assertEqual(service.request_status(), 200)

    def test_malformed_rows_never_change_an_aggregate(self):
        clean = HEADER + "2024-01-01,ALPHA,1.0\n2024-01-02,ALPHA,3.0\n"
        dirty = clean + "2024-01-03,ALPHA,xx\n2024-01-04,,9.9\n"
        with running_service(clean) as clean_service:
            clean_objects, clean_skipped, clean_total = clean_service.report()
        with running_service(dirty) as dirty_service:
            dirty_objects, dirty_skipped, dirty_total = dirty_service.report()
        self.assertEqual(clean_objects, dirty_objects)
        self.assertEqual(clean_total, dirty_total)
        self.assertEqual(clean_skipped, 0)
        self.assertEqual(dirty_skipped, 2)


class DuplicateResolutionTests(unittest.TestCase):
    """AMB-002/REQ: every occurrence of a repeated (date, station) counts."""

    def test_repeated_date_station_rows_all_contribute(self):
        text = HEADER + "2024-01-01,ALPHA,1.0\n" + "2024-01-01,ALPHA,3.0\n"
        with running_service(text) as service:
            objects, _, total = service.report()
            self.assertEqual(len(objects), 1)
            self.assertEqual(objects[0]["count"], 2)
            self.assertEqual(objects[0]["min"], "1.0")
            self.assertEqual(objects[0]["max"], "3.0")
            self.assertEqual(objects[0]["mean"], "2.0")
            self.assertEqual(total, 2)
            self.assertEqual(objects[0], expected_stations(text)["ALPHA"])

    def test_a_new_date_does_not_replace_the_earlier_reading(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,1.0\n"
            + "2024-01-02,ALPHA,2.0\n"
            + "2024-01-03,ALPHA,3.0\n"
        )
        with running_service(text) as service:
            objects, _, total = service.report()
            self.assertEqual(objects[0]["count"], 3)
            self.assertEqual(total, 3)


class RoundingTests(unittest.TestCase):
    """AMB-003/REQ-004: one decimal place, half away from zero."""

    def test_reading_boundaries_round_half_away_from_zero(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,0.05\n"
            + "2024-01-02,ALPHA,-0.05\n"
            + "2024-01-03,ALPHA,1.25\n"
            + "2024-01-04,ALPHA,-1.25\n"
        )
        with running_service(text) as service:
            objects, _, _ = service.report()
            self.assertEqual(objects[0]["min"], "-1.3")
            self.assertEqual(objects[0]["max"], "1.3")
            # mean = (0.05 - 0.05 + 1.25 - 1.25) / 4 = 0.0
            self.assertEqual(objects[0]["mean"], "0.0")

    def test_positive_and_negative_half_means_round_away_from_zero(self):
        positive = HEADER + "2024-01-01,ALPHA,0.0\n2024-01-02,ALPHA,0.1\n"
        negative = HEADER + "2024-01-01,ALPHA,0.0\n2024-01-02,ALPHA,-0.1\n"
        with running_service(positive) as service:
            objects, _, _ = service.report()
            self.assertEqual(objects[0]["mean"], "0.1")
        with running_service(negative) as service:
            objects, _, _ = service.report()
            self.assertEqual(objects[0]["mean"], "-0.1")

    def test_mean_is_exact_before_rounding(self):
        text = (
            HEADER
            + "2024-01-01,ALPHA,-2.0\n"
            + "2024-01-02,ALPHA,-2.0\n"
            + "2024-01-03,ALPHA,-1.9\n"
        )
        with running_service(text) as service:
            objects, _, _ = service.report()
            # -5.9 / 3 = -1.9666..., which is -2.0 at one decimal.
            self.assertEqual(objects[0]["mean"], "-2.0")


class RowOrderTests(unittest.TestCase):
    """REQ-006/REL-001: the summary depends on the multiset of rows only."""

    def test_permuting_the_rows_does_not_change_the_body(self):
        rows = [
            "2024-01-01,ALPHA,10.4",
            "2024-01-01,BRAVO,-2.5",
            "2024-01-02,ALPHA,11.6",
            "2024-01-02,BRAVO,-1.5",
            "2024-01-03,ALPHA,9.5",
            "2024-01-03,BRAVO,-3.5",
        ]
        straight = HEADER + "\n".join(rows) + "\n"
        reversed_rows = HEADER + "\n".join(reversed(rows)) + "\n"
        with running_service(straight) as service:
            straight_body = service.body()
        with running_service(reversed_rows) as service:
            reversed_body = service.body()
        self.assertEqual(straight_body, reversed_body)


class EndpointContractTests(unittest.TestCase):
    """REQ-001/REQ-002: the service stays up, is reached over HTTP and is bounded."""

    def test_the_declared_url_answers_json(self):
        # REQ-001: the declared URL (http://127.0.0.1:{port}/summary) answers
        # 200 with a JSON content type, not a printed text table.
        with running_service(SAMPLE) as service:
            with urllib.request.urlopen(service.url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(
                    "application/json", response.headers.get("Content-Type", "")
                )
                body = response.read().decode("utf-8")
            json.loads(body)

    def test_the_service_does_not_exit_after_answering(self):
        with running_service(SAMPLE) as service:
            self.assertEqual(service.request_status(), 200)
            time.sleep(0.3)
            self.assertIsNone(service.proc.poll())
            self.assertEqual(service.request_status(), 200)

    def test_repeated_requests_answer_identically(self):
        with running_service(SAMPLE) as service:
            first = service.body()
            for _ in range(3):
                self.assertEqual(service.body(), first)

    def test_concurrent_requests_answer_identically(self):
        with running_service(SAMPLE) as service:
            bodies = []
            errors = []

            def fetch():
                try:
                    bodies.append(service.body())
                except Exception as exc:  # noqa: BLE001 - recorded for the assertion
                    errors.append(exc)

            threads = [threading.Thread(target=fetch) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(len(bodies), 8)
            self.assertEqual(len(set(bodies)), 1)

    def test_unknown_path_is_404_and_the_service_stays_up(self):
        with running_service(SAMPLE) as service:
            status = None
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/nope" % service.port, timeout=5)
            except urllib.error.HTTPError as exc:
                status = exc.code
            self.assertEqual(status, 404)
            self.assertEqual(service.request_status(), 200)


class EntryPointTests(unittest.TestCase):
    """REQ-002: how the service is started, and how a bad invocation behaves."""

    def test_missing_arguments_exit_nonzero(self):
        result = subprocess.run(
            ["bash", SERVE], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)

    def test_a_non_numeric_port_exits_nonzero(self):
        handle = write_csv(SAMPLE)
        try:
            result = subprocess.run(
                ["bash", SERVE, handle, "not-a-port"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            os.unlink(handle)
        self.assertEqual(result.returncode, 2)

    def test_an_out_of_range_port_exits_nonzero(self):
        handle = write_csv(SAMPLE)
        try:
            for port in ("0", "70000"):
                result = subprocess.run(
                    ["bash", SERVE, handle, port],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 2)
        finally:
            os.unlink(handle)

    def test_an_unreadable_csv_never_answers(self):
        port = 29999
        result = subprocess.run(
            ["bash", SERVE, "/nonexistent/readings.csv", str(port)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read", result.stderr)

    def test_serve_sh_is_the_declared_entry_point(self):
        self.assertTrue(os.path.isfile(SERVE), "serve.sh must exist at the repository root")
        with open(SERVE, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("station_summary.py", text)


class RequirementDocumentTests(unittest.TestCase):
    """REQ-002: the delivered pipeline runs the delivered tests, not the document."""

    def test_the_document_declares_no_dead_build_or_tests_key(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        doc = os.path.join(root, "docs", "requirements", "service-station-summary.yaml")
        with open(doc, "r", encoding="utf-8") as handle:
            text = handle.read()
        deliverable = text.split("\ndeliverable:", 1)[1]
        self.assertNotIn("\n  build:", deliverable)
        self.assertNotIn("\n  tests:", deliverable)

    def test_the_document_declares_the_run_and_read_contract(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        doc = os.path.join(root, "docs", "requirements", "service-station-summary.yaml")
        with open(doc, "r", encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn('run: "bash serve.sh {csv} {port}"', text)
        self.assertIn('read: "curl -fsS {url}"', text)
        self.assertIn("timeoutMs: 120000", text)

    def test_the_document_bounds_the_start_and_serve_command(self):
        # `bash serve.sh {csv} {port}` never exits on its own (REQ-002), so the
        # document must declare a bound; without one a judge waits for ever.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        doc = os.path.join(root, "docs", "requirements", "service-station-summary.yaml")
        with open(doc, "r", encoding="utf-8") as handle:
            text = handle.read()
        deliverable = text.split("\ndeliverable:", 1)[1]
        timeout = re.search(r"(?m)^  timeoutMs: ([0-9]+)$", deliverable)
        self.assertIsNotNone(timeout, "the deliverable must declare a timeoutMs bound")
        self.assertGreater(int(timeout.group(1)), 0)


class OfflineOperationTests(unittest.TestCase):
    """REQ-007: the service runs with no network access and makes no outbound call."""

    def test_the_same_summary_is_served_with_outbound_networking_blocked(self):
        blocked = dict(os.environ)
        blocked.update(
            {
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "http_proxy": "http://127.0.0.1:9",
                "https_proxy": "http://127.0.0.1:9",
                "NO_PROXY": "",
                "no_proxy": "",
            }
        )
        with running_service(SAMPLE) as baseline:
            baseline_body = baseline.body()
        with running_service(SAMPLE, env=blocked) as offline:
            offline_body = offline.body()
        self.assertEqual(offline_body, baseline_body)

    def test_the_offline_body_is_still_the_declared_summary(self):
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
        with running_service(SAMPLE, env=blocked) as service:
            self.assertEqual(service.request_status(), 200)
            objects, skipped, total = service.report()
            self.assertEqual(total, expected_total(SAMPLE))
            self.assertEqual(skipped, expected_skipped(SAMPLE))
            self.assertEqual({obj["station"]: obj for obj in objects}, expected_stations(SAMPLE))

    def test_the_service_makes_no_outbound_network_import(self):
        # The service binds 127.0.0.1 with http.server and never imports an
        # outbound HTTP client, so it cannot reach the network even when one is
        # available.  http.server is the inbound listener and is allowed.
        service_source = os.path.join(ROOT, "station_summary.py")
        with open(service_source, "r", encoding="utf-8") as handle:
            source = handle.read()
        for module in ("http.client", "requests", "ftplib", "smtplib", "telnetlib"):
            self.assertNotRegex(
                source, r"(?m)^\s*(?:import|from)\s+%s\b" % re.escape(module)
            )
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("urlopen", source)


class PerformanceTests(unittest.TestCase):
    """REQ-007: a year of readings is summarised in a couple of seconds."""

    def test_two_hundred_thousand_rows_are_summarised_promptly(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        try:
            handle.write(HEADER)
            for index in range(200000):
                day = index % 28 + 1
                month = index % 12 + 1
                station = "STATION%05d" % (index % 500)
                value = (index % 400) / 10.0 - 20.0
                handle.write("%04d-%02d-%02d,%s,%.1f\n" % (2024, month, day, station, value))
            handle.close()
            start = time.monotonic()
            service_proc = subprocess.Popen(
                ["bash", SERVE, handle.name, str(_free_port())],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                # The service parses before it binds, so a quick 200 means the
                # whole fixture was summarised within the budget.
                port = int(service_proc.args[3])
                deadline = time.monotonic() + 60
                answered = False
                while time.monotonic() < deadline:
                    if service_proc.poll() is not None:
                        message = service_proc.stderr.read().decode("utf-8", "replace")
                        raise AssertionError("serve.sh exited early: %s" % message)
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:%d/summary" % port, timeout=5
                        ) as response:
                            body = response.read()
                        answered = True
                        break
                    except OSError:
                        time.sleep(0.1)
                elapsed = time.monotonic() - start
                self.assertTrue(answered, "the service never answered for 200,000 rows")
                self.assertLess(elapsed, 60)
                self.assertIn(b'"total":200000', body)
            finally:
                if service_proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(service_proc.pid), 15)
                    except (ProcessLookupError, PermissionError):
                        service_proc.terminate()
                    service_proc.wait(timeout=10)
                if service_proc.stderr is not None:
                    service_proc.stderr.close()
        finally:
            os.unlink(handle.name)


def _free_port():
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


if __name__ == "__main__":
    unittest.main()
