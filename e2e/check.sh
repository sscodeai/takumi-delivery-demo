#!/usr/bin/env bash
# e2e/check.sh -- the end-to-end CLI check the confirmed requirement declares.
#
#   usage: bash e2e/check.sh <csv-path>
#
# The confirmed requirement document names this check as the deliverable's
# scenario (SCN-001):
#
#   scenarios:
#     - id: SCN-001
#       run: "bash e2e/check.sh {csv}"
#       expect: "the CLI prints one station line per distinct station with
#                count, min, max and mean, exactly one TOTAL line and exactly
#                one SKIPPED line"
#       report: ctrf
#       report_path: "e2e/report.json"
#
# It runs the delivered entry point exactly as the document names it
# (`bash summary.sh <csv-path>`), checks the printed report against an
# independent recomputation of the document's declared world and against the
# declared output contract, writes a CTRF report to e2e/report.json, and exits
# 0 only when every check passed.
#
# The independent recomputation is deliberately a second implementation of the
# same contract: it reads the CSV through Python's csv module, keeps the values
# as exact rationals (fractions.Fraction) and rounds half away from zero with
# integer arithmetic, so a defect in summary.sh cannot be hidden by a shared
# code path and binary floating point cannot distort a boundary value.
set -uo pipefail

if [ "$#" -ne 1 ]; then
  printf 'usage: bash e2e/check.sh <csv-path>\n' >&2
  exit 2
fi

CSV="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
REPORT="$SCRIPT_DIR/report.json"

if [ ! -f "$CSV" ]; then
  printf 'e2e/check.sh: input file not found: %s\n' "$CSV" >&2
  exit 2
fi
if [ ! -r "$CSV" ]; then
  printf 'e2e/check.sh: input file is not readable: %s\n' "$CSV" >&2
  exit 2
fi

python3 - "$CSV" "$ROOT" "$REPORT" <<'PY'
"""Drive summary.sh over one CSV and write the declared CTRF report."""

import csv
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from fractions import Fraction

csv_path, root, report_path = sys.argv[1], sys.argv[2], sys.argv[3]
summary = os.path.join(root, "summary.sh")

# The declared world (docs/requirements/intake.yaml, deliverable.input_format):
# columns date:date,station:id,temperature_c:measure. A row is valid when it has
# one field per declared column, a non-empty station id, a calendar-valid ISO
# date (an optional time suffix is accepted) and a plain decimal temperature.
DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(.*)$")
TEMP_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")
HEADER_NAMES = ("date", "station", "temperature_c")


def is_date(text):
    match = DATE_RE.match(text)
    if match is None:
        return False
    year, month, day = (int(part) for part in match.groups()[:3])
    try:
        date(year, month, day)
    except ValueError:
        return False
    suffix = match.group(4)
    if suffix == "":
        return True
    if suffix[0] not in "T ":
        return False
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_temperature(text):
    return TEMP_RE.match(text) is not None


def one_decimal(value):
    """Render ``value`` (already scaled by ten) with one decimal, half away
    from zero."""
    numerator, denominator = value.numerator, value.denominator
    negative = numerator < 0
    if negative:
        numerator = -numerator
    quotient, remainder = divmod(numerator, denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    if quotient == 0:
        return "0.0"
    return "%s%d.%d" % ("-" if negative else "", quotient // 10, quotient % 10)


def read_rows(handle):
    reader = csv.reader(handle)
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error:
            yield None


def recompute(path):
    """The declared report for ``path``, computed independently of summary.sh."""
    stations = {}
    skipped = 0
    total = 0
    header_seen = False
    date_i, station_i, temperature_i = 0, 1, 2
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in read_rows(handle):
            if row is None:
                skipped += 1
                continue
            if not header_seen:
                header_seen = True
                names = [column.strip().lower() for column in row]
                if all(name in names for name in HEADER_NAMES):
                    date_i = names.index("date")
                    station_i = names.index("station")
                    temperature_i = names.index("temperature_c")
                    continue
            if len(row) != 3:
                skipped += 1
                continue
            station = row[station_i]
            if station == "":
                skipped += 1
                continue
            if not is_date(row[date_i]):
                skipped += 1
                continue
            if not is_temperature(row[temperature_i]):
                skipped += 1
                continue
            value = Fraction(row[temperature_i])
            entry = stations.get(station)
            if entry is None:
                stations[station] = [1, value, value, value]
            else:
                entry[0] += 1
                if value < entry[1]:
                    entry[1] = value
                if value > entry[2]:
                    entry[2] = value
                entry[3] += value
            total += 1

    lines = []
    # Station lines are emitted in ascending byte-wise station id order.
    for station in sorted(stations, key=lambda name: name.encode("utf-8")):
        count, minimum, maximum, accumulated = stations[station]
        lines.append(
            "%s %d %s %s %s"
            % (
                station,
                count,
                one_decimal(minimum * 10),
                one_decimal(maximum * 10),
                one_decimal((accumulated / count) * 10),
            )
        )
    lines.append("SKIPPED %d" % skipped)
    lines.append("TOTAL %d" % total)
    return lines


def classify(line):
    """'G' station line, 'T' totals line, 'S' skipped line, 'X' unrecognised."""
    parts = line.split(" ")
    if len(parts) == 2 and parts[0] == "TOTAL":
        return "T"
    if len(parts) == 2 and parts[0] == "SKIPPED":
        return "S"
    if len(parts) == 5:
        return "G"
    return "X"


def parse_station(line):
    parts = line.split(" ")
    return {
        "id": parts[0],
        "count": parts[1],
        "min": parts[2],
        "max": parts[3],
        "mean": parts[4],
    }


tests = []


def check(name, ok, detail=""):
    tests.append(
        {
            "name": name,
            "status": "passed" if ok else "failed",
            "duration": 0,
            "message": "" if ok else detail,
        }
    )


try:
    proc = subprocess.run(
        ["bash", summary, csv_path],
        capture_output=True,
        text=True,
        timeout=110,
    )
    status = proc.returncode
    tool_out = proc.stdout
    tool_err = proc.stderr
except subprocess.TimeoutExpired:
    status = 124
    tool_out = ""
    tool_err = "the deliverable did not exit within 110s"

expected = recompute(csv_path)
expected_text = "\n".join(expected)

# REQ-001: the declared entry point runs and exits 0 on a readable file.
check(
    "REQ-001 summary.sh exits 0 on a readable input file",
    status == 0,
    "exit=%s stderr=%s" % (status, tool_err.strip()[:200]),
)

# The declared output contract: one station line per distinct station with
# count, min, max and mean, exactly one TOTAL line and exactly one SKIPPED line.
lines = [line for line in tool_out.split("\n") if line != ""]
station_lines = [line for line in lines if classify(line) == "G"]
total_lines = [line for line in lines if classify(line) == "T"]
skip_lines = [line for line in lines if classify(line) == "S"]
unrecognised = [line for line in lines if classify(line) == "X"]

# REQ-002/REQ-003/REQ-004 + DIFF-001: the whole report equals the independent
# recomputation of the declared world.
check(
    "REQ-002..005 the printed report equals an independent recomputation",
    tool_out.rstrip("\n") == expected_text,
    "printed=%r expected=%r" % (tool_out.rstrip("\n"), expected_text),
)

# REQ-003: exactly one totals line.
check(
    "REQ-003 exactly one TOTAL line",
    len(total_lines) == 1,
    "found %d TOTAL line(s)" % len(total_lines),
)

# REQ-004: exactly one skipped line, present even when nothing was skipped.
check(
    "REQ-004 exactly one SKIPPED line",
    len(skip_lines) == 1,
    "found %d SKIPPED line(s)" % len(skip_lines),
)

# REQ-002: exactly one station line per distinct station id.
station_ids = [parse_station(line)["id"] for line in station_lines]
check(
    "REQ-002 one station line per distinct station id",
    len(station_ids) == len(set(station_ids)),
    "duplicate station line(s): %s" % ", ".join(sorted(station_ids)),
)

check(
    "REQ-002 every line matches a declared output shape",
    not unrecognised,
    "unrecognised line(s): %r" % unrecognised[:3],
)

# REQ-002: each station line has five fields in the order id,count,min,max,mean
# with count an integer, min <= mean <= max, and min/max/mean carrying exactly
# one decimal place.
shape_ok = True
shape_detail = ""
for line in station_lines:
    fields = parse_station(line)
    if not re.match(r"^-?[0-9]+\.[0-9]$", fields["min"]) or not re.match(
        r"^-?[0-9]+\.[0-9]$", fields["max"]
    ) or not re.match(r"^-?[0-9]+\.[0-9]$", fields["mean"]):
        shape_ok = False
        shape_detail = "line not one-decimal: %r" % line
        break
    if not re.match(r"^[0-9]+$", fields["count"]) or int(fields["count"]) < 1:
        shape_ok = False
        shape_detail = "count is not a positive integer: %r" % line
        break
    low, high, mean = float(fields["min"]), float(fields["max"]), float(fields["mean"])
    if not (low <= mean <= high):
        shape_ok = False
        shape_detail = "min <= mean <= max does not hold: %r" % line
        break
check(
    "REQ-002 station lines carry count, min, max, mean with one decimal place",
    shape_ok,
    shape_detail,
)

# REQ-002: station lines appear in ascending byte-wise station id order.
check(
    "REQ-002 station lines are in ascending byte-wise order",
    station_ids == sorted(station_ids, key=lambda name: name.encode("utf-8")),
    "order=%r" % station_ids,
)

# REL-002: the per-station counts sum to the TOTAL count the tool printed, and
# the tool's station set equals the recomputed one.
counts_sum = sum(int(parse_station(line)["count"]) for line in station_lines)
total_value = int(total_lines[0].split(" ")[1]) if len(total_lines) == 1 else None
check(
    "REL-002 the per-station counts sum to the TOTAL count",
    total_value is not None and counts_sum == total_value,
    "counts sum to %d but TOTAL is %s" % (counts_sum, total_value),
)
expected_ids = [line.split(" ")[0] for line in expected if classify(line) == "G"]
check(
    "REQ-006 the station set equals the recomputed station set",
    station_ids == expected_ids,
    "tool=%r expected=%r" % (station_ids, expected_ids),
)

failed = [test for test in tests if test["status"] != "passed"]
report = {
    "reportFormat": "CTRF",
    "specVersion": "0.0.0",
    "results": {
        "tool": {"name": "e2e/check.sh"},
        "summary": {
            "tests": len(tests),
            "passed": len(tests) - len(failed),
            "failed": len(failed),
            "pending": 0,
            "skipped": 0,
            "other": 0,
            "start": 0,
            "stop": 0,
        },
        "tests": tests,
    },
}

os.makedirs(os.path.dirname(report_path), exist_ok=True)
with open(report_path, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2)
    handle.write("\n")

for test in tests:
    print("%s %s" % ("ok" if test["status"] == "passed" else "not ok", test["name"]))
    if test["status"] != "passed" and test.get("message"):
        print("  %s" % test["message"])
print(
    "e2e/check.sh: %d check(s), %d failed -> %s"
    % (len(tests), len(failed), report_path)
)

sys.exit(1 if failed else 0)
PY
