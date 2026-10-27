#!/usr/bin/env python3
"""Mutation harness for the delivered summary tool.

Each entry below is one deliberate defect applied to ``summary.py``. The
harness copies the delivered files into a throwaway directory, applies ONE
defect, runs the delivered suite (``bash run-tests.sh``) against the mutant and
records whether the suite noticed. A mutant the suite still passes is a
SURVIVOR -- a gap in the tests.

The report is the tool-agnostic survivors-json shape::

    {"total": <mutants measured>,
     "survivors": [{"file": ..., "line": ..., "description": ...}, ...]}

It is written to ``reports/mutation/mutation.json`` whether or not there are
survivors, and the harness exits non-zero when any mutant survives.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = "summary.py"
REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")
DELIVERY_FILES = (
    "summary.sh",
    "summary.py",
    "run-tests.sh",
    os.path.join("tests", "test_summary.py"),
)
MUTANT_TIMEOUT_S = 300

# (description, exact text in summary.py, replacement). Each one changes a
# behaviour the delivered suite is supposed to defend, so a survivor is a real
# test gap.
MUTATIONS = (
    (
        "AMB-001 half-up rounding: an exact half no longer rounds away from zero",
        "    if remainder * 2 >= denominator:",
        "    if remainder * 2 > denominator:",
    ),
    (
        "REQ-004 percentage scale: report a 0..1 fraction instead of percentage points",
        "    return render_tenths(passed * 1000 / total)",
        "    return render_tenths(passed * 10 / total)",
    ),
    (
        "REQ-004 one-decimal rendering: drop the fractional percentage digit",
        '    return "%s%d.%d" % ("-" if negative else "", whole // 10, whole % 10)',
        '    return "%s%d.0" % ("-" if negative else "", whole // 10)',
    ),
    (
        "AMB-002 merge: keep the last passed count instead of summing occurrences",
        "            entry[0] += passed",
        "            entry[0] = passed",
    ),
    (
        "REQ-003 ordering: sort suites by name instead of first appearance",
        "    for suite, (passed, total) in merged.items():",
        "    for suite, (passed, total) in sorted(merged.items()):",
    ),
    (
        "REQ-003 verbatim suite names: fold the suite id to lower case",
        '    suite = row[columns["suite"]]',
        '    suite = row[columns["suite"]].lower()',
    ),
    (
        "REQ-005 TOTAL: count passed instead of total",
        "        total_tests += total",
        "        total_tests += passed",
    ),
    (
        "REQ-002 header lookup: read columns by position instead of by name",
        "        return {name: names.index(name) for name in HEADER_NAMES}, True",
        "        return dict(DEFAULT_COLUMNS), True",
    ),
    (
        "AMB-003 zero-total guard: divide by a zero total instead of skipping the row",
        "    if total == 0:\n        return None",
        "    if total == 0:\n        return suite, Fraction(0), total",
    ),
)


def line_number(text, needle):
    index = text.find(needle)
    if index < 0:
        raise SystemExit("mutation harness: anchor not found in %s: %r" % (TARGET, needle))
    return text.count("\n", 0, index) + 1


def build_mutant(directory, original, needle, replacement):
    for relative in DELIVERY_FILES:
        source = os.path.join(ROOT, relative)
        destination = os.path.join(directory, relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
    mutated = original.replace(needle, replacement, 1)
    if mutated == original:
        raise SystemExit("mutation harness: replacement did not change %s" % TARGET)
    with open(os.path.join(directory, TARGET), "w", encoding="utf-8") as handle:
        handle.write(mutated)


def run_suite(directory):
    environment = dict(os.environ)
    environment["TAP_OUT"] = os.path.join(directory, "reports", "tests.tap")
    try:
        proc = subprocess.run(
            ["bash", "run-tests.sh"],
            cwd=directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=MUTANT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return 124
    return proc.returncode


def write_report(total, survivors):
    directory = os.path.dirname(REPORT)
    os.makedirs(directory, exist_ok=True)
    payload = {"total": total, "survivors": survivors}
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main():
    with open(os.path.join(ROOT, TARGET), encoding="utf-8") as handle:
        original = handle.read()

    survivors = []
    for index, (description, needle, replacement) in enumerate(MUTATIONS, 1):
        line = line_number(original, needle)
        with tempfile.TemporaryDirectory(prefix="summary-mutant-") as directory:
            build_mutant(directory, original, needle, replacement)
            status = run_suite(directory)
        if status == 0:
            print("not ok %d - survived: %s" % (index, description))
            survivors.append({"file": TARGET, "line": line, "description": description})
        else:
            print("ok %d - killed: %s" % (index, description))

    write_report(len(MUTATIONS), survivors)
    print("# mutants %d" % len(MUTATIONS))
    print("# survivors %d" % len(survivors))
    print("# report %s" % os.path.relpath(REPORT, ROOT))
    if survivors:
        print("# the delivered tests do not notice the mutations listed above")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
