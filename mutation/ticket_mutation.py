#!/usr/bin/env python3
"""Mutation harness for the delivered ticket-summary tool.

Each mutant below is one deliberate defect applied to ``ticket_summary.py``.
The harness copies the delivered files into a throwaway directory, applies ONE
defect, runs the delivered suite (``bash run-tests.sh``) against the mutant and
records whether the suite noticed.  A mutant the suite still passes is a
SURVIVOR -- a gap in the tests.

The tool-agnostic verdict is written to ``reports/mutation/mutation.json``::

    {"total": <mutants measured>,
     "survivors": [{"file": ..., "line": ..., "description": ...}, ...]}

``total`` counts the mutants measured and is at least 1; against the correct
implementation ``survivors`` is empty.  Human-readable TAP-ish progress goes to
stdout and the harness exits non-zero when any mutant survives.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = "ticket_summary.py"
REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")
DELIVERY_FILES = (
    "ticket-summary.sh",
    "ticket_summary.py",
    "run-tests.sh",
    os.path.join("tests", "test_ticket_summary.py"),
    os.path.join("tests", "test_ticket_summary_units.py"),
)
MUTANT_TIMEOUT_S = 300
WORKERS = 4

# (description, exact text in ticket_summary.py, replacement).  Each one changes
# a behaviour the delivered suite is supposed to defend, so a survivor is a real
# test gap.
MUTATIONS = (
    (
        "REQ-003/REQ-004: count every open ticket as closed and vice versa",
        '        bucket[0 if kind == "open" else 1] += 1',
        '        bucket[1 if kind == "open" else 0] += 1',
    ),
    (
        "REQ-004 TOTAL: forget every open count in the total",
        "        open_total += open_count",
        "        open_total += 0",
    ),
    (
        "REQ-004 TOTAL: forget every closed count in the total",
        "        closed_total += closed_count",
        "        closed_total += 0",
    ),
    (
        "REQ-003 ordering: keep insertion order instead of byte order",
        '    return sorted(counts, key=lambda name: name.encode("utf-8"))',
        "    return list(counts)",
    ),
    (
        "AMB-003: merge assignees case-insensitively instead of keeping spelling",
        "        bucket = counts.setdefault(assignee, [0, 0])",
        "        bucket = counts.setdefault(assignee.casefold(), [0, 0])",
    ),
    (
        "AMB-004: treat repeated identical rows as one ticket",
        '        bucket[0 if kind == "open" else 1] += 1',
        '        bucket[0 if kind == "open" else 1] = 1',
    ),
    (
        "REQ-006 skipped: never count a row with the wrong number of fields",
        "        if len(record) != width:\n            skipped += 1",
        "        if len(record) != width:\n            skipped += 0",
    ),
    (
        "REQ-006 skipped: never count an empty-assignee/empty-status/unknown row",
        "        if not assignee or not status or kind is None:\n"
        "            # AMB-002 (skip-count): an empty assignee, an empty status or an\n"
        "            # unrecognised status also makes the row unusable and skippable.\n"
        "            skipped += 1",
        "        if not assignee or not status or kind is None:\n"
        "            # AMB-002 (skip-count): an empty assignee, an empty status or an\n"
        "            # unrecognised status also makes the row unusable and skippable.\n"
        "            skipped += 0",
    ),
    (
        "AMB-001: count an unrecognised status as closed instead of skipping it",
        '    if status == CLOSED:\n        return "closed"\n    return None',
        '    if status == CLOSED:\n        return "closed"\n    return "closed"',
    ),
    (
        "REQ-006: accept an empty assignee as an assignee",
        "        if not assignee or not status or kind is None:",
        "        if not status or kind is None:",
    ),
    (
        "REQ-006 field count: accept a row with extra fields",
        "        if len(record) != width:",
        "        if len(record) < width:",
    ),
    (
        "REQ-003/REQ-005: stop trimming and case-folding the status value",
        "    status = value.strip().casefold()",
        "    status = value.casefold()",
    ),
    (
        "REQ-003: group by the untrimmed assignee string",
        "        assignee = record[assignee_index].strip()",
        "        assignee = record[assignee_index]",
    ),
    (
        "REQ-002 header: match column names without folding case",
        "        name = cell.strip().casefold()",
        "        name = cell.strip()",
    ),
    (
        "AMB-005: split quoted fields on commas instead of honouring quoting",
        "            return list(csv.reader(handle))",
        "            return list(csv.reader(handle, quoting=csv.QUOTE_NONE))",
    ),
    (
        "REQ-006 skipped: stay silent when nothing was skipped",
        '    sys.stderr.write(\n'
        '        "skipped %d %s\\n" % (skipped, "row" if skipped == 1 else "rows")\n'
        "    )",
        "    if skipped:\n"
        "        sys.stderr.write(\n"
        '            "skipped %d %s\\n" % (skipped, "row" if skipped == 1 else "rows")\n'
        "        )",
    ),
)


def anchor(text, needle):
    """Return the 1-based line of a unique needle in the source."""
    index = text.find(needle)
    if index < 0:
        raise SystemExit("mutation harness: anchor not found in %s: %r" % (TARGET, needle))
    if text.find(needle, index + 1) >= 0:
        raise SystemExit("mutation harness: anchor is not unique in %s: %r" % (TARGET, needle))
    return text.count("\n", 0, index) + 1


def build_mutants(original):
    mutants = []
    for index, (description, needle, replacement) in enumerate(MUTATIONS, 1):
        mutants.append(
            {
                "id": index,
                "description": description,
                "needle": needle,
                "replacement": replacement,
                "line": anchor(original, needle),
            }
        )
    return mutants


def copy_delivery(directory):
    for relative in DELIVERY_FILES:
        source = os.path.join(ROOT, relative)
        destination = os.path.join(directory, relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)


def run_suite(directory, timeout):
    """Run the delivered suite in *directory*.

    Returns ``(exit_status, failure_reported)`` where *failure_reported* is true
    when either delivered TAP report contains a ``not ok`` line.  REQ-007
    requires a deliberately broken implementation to fail with a visible
    ``not ok`` line, not merely a non-zero exit, so the harness checks both.
    """
    environment = dict(os.environ)
    environment["TAP_OUT"] = os.path.join(directory, "reports", "tests.tap")
    try:
        proc = subprocess.run(
            ["bash", "run-tests.sh"],
            cwd=directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, False
    failure_reported = False
    for relative in ("reports/tests.tap", "reports/tests-ticket-units.tap"):
        try:
            with open(os.path.join(directory, relative), "r", encoding="utf-8") as handle:
                if any(
                    line.lstrip().startswith("not ok")
                    for line in handle.read().splitlines()
                ):
                    failure_reported = True
        except OSError:
            continue
    return proc.returncode, failure_reported


def baseline_passes():
    with tempfile.TemporaryDirectory(prefix="ticket-baseline-") as directory:
        copy_delivery(directory)
        status, _ = run_suite(directory, MUTANT_TIMEOUT_S)
        return status == 0


def measure(original, mutant):
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ticket-mutant-") as directory:
        copy_delivery(directory)
        mutated = original.replace(mutant["needle"], mutant["replacement"], 1)
        if mutated == original:
            raise SystemExit("mutation harness: replacement did not change %s" % TARGET)
        with open(os.path.join(directory, TARGET), "w", encoding="utf-8") as handle:
            handle.write(mutated)
        status, failure_reported = run_suite(directory, MUTANT_TIMEOUT_S)
    return {
        "mutant": mutant,
        "status": status,
        "failureReported": failure_reported,
        "killed": status != 0 and failure_reported,
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def main():
    with open(os.path.join(ROOT, TARGET), "r", encoding="utf-8") as handle:
        original = handle.read()

    mutants = build_mutants(original)

    if not baseline_passes():
        sys.stderr.write(
            "mutation harness: the delivered suite fails on the unmutated source, "
            "so no mutant verdict would be meaningful\n"
        )
        return 2

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda mutant: measure(original, mutant), mutants))

    survivors = []
    for result in results:
        mutant = result["mutant"]
        if result["killed"]:
            verdict = "killed"
        else:
            verdict = "SURVIVED"
            if result["status"] != 0 and not result["failureReported"]:
                reason = "suite failed but wrote no 'not ok' line"
            else:
                reason = "suite still passes the mutant"
            survivors.append(
                {
                    "file": TARGET,
                    "line": mutant["line"],
                    "description": "%s [%s]" % (mutant["description"], reason),
                }
            )
        print(
            "mutant %d %s - %s (exit %d, %d ms)"
            % (
                mutant["id"],
                verdict,
                mutant["description"],
                result["status"],
                result["durationMs"],
            )
        )

    report = {"total": len(mutants), "survivors": survivors}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(
        "%d mutants measured, %d survivors -> %s"
        % (len(mutants), len(survivors), os.path.relpath(REPORT, ROOT))
    )
    return 0 if not survivors else 1


if __name__ == "__main__":
    sys.exit(main())
