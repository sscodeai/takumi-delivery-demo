"""Shared helpers for the summary.sh test suite.

Every test drives the delivered entry point the way the requirement document
names it (`bash summary.sh <csv>`) through a process boundary, so the tests
exercise the real script rather than an imported function.
"""

import os
import re
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "summary.sh")
HEADER = "date,station,temperature_c\n"

STATION_SHAPE = re.compile(r"^\S+ [0-9]+ -?[0-9]+\.[0-9] -?[0-9]+\.[0-9] -?[0-9]+\.[0-9]$")


def run_csv(text, env=None, cwd=None, timeout=180):
    """Write text to a temporary CSV and run the deliverable on it."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    try:
        handle.write(text)
        handle.close()
        return subprocess.run(
            ["bash", SCRIPT, handle.name],
            cwd=cwd or ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    finally:
        os.unlink(handle.name)


def station_lines(stdout):
    return [
        line
        for line in stdout.splitlines()
        if line and not line.startswith(("SKIPPED ", "TOTAL "))
    ]


def skipped_of(stdout):
    return int(
        next(line for line in stdout.splitlines() if line.startswith("SKIPPED ")).split(" ")[1]
    )


def total_of(stdout):
    return int(next(line for line in stdout.splitlines() if line.startswith("TOTAL ")).split(" ")[1])


def names_in_order(stdout):
    return [line.split(" ")[0] for line in stdout.splitlines() if line]


def counts_sum(stdout):
    return sum(int(line.split(" ")[1]) for line in station_lines(stdout))
