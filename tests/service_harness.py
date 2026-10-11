"""Harness for the station temperature summary HTTP service tests.

The harness starts the real entry point the requirement document names
(``bash serve.sh <csv> <port>``) through a process boundary, waits for the
declared URL (``http://127.0.0.1:<port>/summary``) and reads the JSON report.
Nothing here imports the implementation, so the tests judge the delivered
surface rather than an in-process function.
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
import urllib.error
import urllib.request
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVE = os.path.join(ROOT, "serve.sh")
SUMMARY_URL = "http://127.0.0.1:%d/summary"

# The declared output shapes, as the requirement document states them.  A line
# served by the endpoint must match exactly one of these compact JSON objects.
STATION_LINE = re.compile(
    r'^\{"station":"(?P<station>(?:[^"\\]|\\.)*)",'
    r'"count":(?P<count>[0-9]+),'
    r'"min":(?P<min>-?[0-9]+\.[0-9]),'
    r'"max":(?P<max>-?[0-9]+\.[0-9]),'
    r'"mean":(?P<mean>-?[0-9]+\.[0-9])\}$'
)
SKIPPED_LINE = re.compile(r'^\{"skipped":(?P<skipped>[0-9]+)\}$')
TOTAL_LINE = re.compile(r'^\{"total":(?P<total>[0-9]+)\}$')


def free_port():
    """A localhost port nothing is listening on right now."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def parse_body(body):
    """Read a response body as the declared report.

    The body is one valid JSON array and one declared object per line at the
    same time, so it is checked both ways: ``json.loads`` must accept the whole
    document, and every element line must match its declared shape exactly.
    """
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "[" or lines[-1] != "]":
        raise AssertionError("the response is not a JSON array framed line-wise: %r" % text)
    objects = []
    skipped = []
    totals = []
    for line in lines[1:-1]:
        if line.strip() == ",":
            # The array separator is on its own line so every object line can
            # match a declared shape anchored at the end.
            continue
        stripped = line.rstrip(",")
        match = STATION_LINE.match(stripped)
        if match is not None:
            objects.append(
                {
                    "station": json.loads('"%s"' % match.group("station")),
                    "count": int(match.group("count")),
                    "min": match.group("min"),
                    "max": match.group("max"),
                    "mean": match.group("mean"),
                }
            )
            continue
        match = SKIPPED_LINE.match(stripped)
        if match is not None:
            skipped.append(int(match.group("skipped")))
            continue
        match = TOTAL_LINE.match(stripped)
        if match is not None:
            totals.append(int(match.group("total")))
            continue
        raise AssertionError("response line matches no declared shape: %r" % line)
    if len(skipped) != 1 or len(totals) != 1:
        raise AssertionError(
            "the response must carry exactly one skipped and one total object: %r" % text
        )
    document = json.loads(text)
    if not isinstance(document, list):
        raise AssertionError("the whole response is not a JSON array: %r" % text)
    normalised = []
    for element in document:
        if "station" in element:
            normalised.append(
                {
                    "station": element["station"],
                    "count": element["count"],
                    "min": "%.1f" % element["min"],
                    "max": "%.1f" % element["max"],
                    "mean": "%.1f" % element["mean"],
                }
            )
        else:
            normalised.append(element)
    if normalised != objects + [{"skipped": skipped[0]}, {"total": totals[0]}]:
        raise AssertionError("the JSON array and the declared lines disagree: %r" % text)
    return objects, skipped[0], totals[0]


@contextmanager
def running_service(text, wait_seconds=20, env=None):
    """Write ``text`` to a CSV and yield a started service over it.

    ``env`` overrides the environment the service process is started with, so a
    test can assert the summary is unchanged when outbound networking is
    unavailable (REQ-007).
    """
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    try:
        handle.write(text)
        handle.close()
        service = Service(handle.name, wait_seconds=wait_seconds, env=env)
        try:
            yield service
        finally:
            service.stop()
    finally:
        os.unlink(handle.name)


class Service:
    """The delivered service, started the way the requirement document declares."""

    def __init__(self, path, wait_seconds=20, env=None):
        self.path = path
        self.port = free_port()
        self.proc = subprocess.Popen(
            ["bash", SERVE, path, str(self.port)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
        try:
            self._wait_for_url(wait_seconds)
        except BaseException:
            self.stop()
            raise

    @property
    def url(self):
        return SUMMARY_URL % self.port

    def _wait_for_url(self, wait_seconds):
        deadline = time.monotonic() + wait_seconds
        last_error = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                message = self.proc.stderr.read().decode("utf-8", "replace")
                raise AssertionError(
                    "serve.sh exited %s before answering: %s"
                    % (self.proc.returncode, message)
                )
            try:
                status = self.request_status()
            except OSError as exc:
                last_error = exc
                status = None
            if status is not None:
                return
            time.sleep(0.1)
        raise AssertionError("the service did not answer on %s: %s" % (self.url, last_error))

    def request_status(self, timeout=2):
        request = urllib.request.Request(self.url)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def body(self, timeout=10):
        with urllib.request.urlopen(self.url, timeout=timeout) as response:
            if response.status != 200:
                raise AssertionError("GET %s answered HTTP %s" % (self.url, response.status))
            return response.read()

    def report(self, timeout=10):
        return parse_body(self.body(timeout))

    def stop(self):
        proc = getattr(self, "proc", None)
        if proc is None:
            return
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                proc.wait(timeout=5)
        if proc.stderr is not None:
            proc.stderr.close()
