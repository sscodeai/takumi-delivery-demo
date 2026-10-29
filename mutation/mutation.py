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
    os.path.join("tests", "test_units.py"),
)
MUTANT_TIMEOUT_S = 300

# (description, exact text in summary.py, replacement). Each one changes a
# behaviour the delivered suite is supposed to defend, so a survivor is a real
# test gap.
MUTATIONS = (
    (
        "AMB-003 half-up: an exact half no longer rounds away from zero",
        "    if remainder * 2 >= denominator:",
        "    if remainder * 2 > denominator:",
    ),
    (
        "REQ-007 money format: print one decimal instead of exactly two",
        '    return "%s%d.%02d" % ("-" if negative else "", whole // 100, whole % 100)',
        '    return "%s%d.%d" % ("-" if negative else "", whole // 100, (whole % 100) // 10)',
    ),
    (
        "REQ-003 mean: divide by a different count than the group's rows",
        "format_money(amount / count)",
        "format_money(amount / (count + 1))",
    ),
    (
        "REQ-004 TOTAL sum: forget every region's revenue",
        "        total += amount",
        "        total += Fraction(0)",
    ),
    (
        "REQ-004 TOTAL count: count regions instead of accepted rows",
        '    lines.append("TOTAL %d %s" % (accepted, format_money(total)))',
        '    lines.append("TOTAL %d %s" % (len(groups), format_money(total)))',
    ),
    (
        "REQ-005 SKIPPED: never count a malformed row",
        "            skipped += 1",
        "            skipped += 0",
    ),
    (
        "REQ-005 field count: accept a row with extra fields",
        "    if len(record) != 2:",
        "    if len(record) < 2:",
    ),
    (
        "REQ-005 amount: accept surrounding blanks as part of a plain decimal",
        'AMOUNT = re.compile(r"^[+-]?[0-9]+(?:\\.[0-9]+)?$")',
        'AMOUNT = re.compile(r"^\\s*[+-]?[0-9]+(?:\\.[0-9]+)?\\s*$")',
    ),
    (
        "REQ-002 header: accept any first record as a header",
        "    if tuple(cells) != HEADER:",
        "    if False:",
    ),
    (
        "REQ-002 header: match names without trimming or case folding",
        "    cells = [cell.strip().lower() for cell in record]",
        "    cells = [cell for cell in record]",
    ),
    (
        "REQ-003 region: group by the untrimmed region string",
        "    region = record[0].strip()",
        "    region = record[0]",
    ),
    (
        "REQ-003/REQ-009 ordering: keep insertion order instead of sorting",
        '    for region in sorted(groups, key=lambda name: name.encode("utf-8")):',
        "    for region in groups:",
    ),
    (
        "AMB-002 duplicate rows: keep the row count at one per region",
        "            group[0] += 1",
        "            group[0] = 1",
    ),
    (
        "AMB-002 duplicate rows: keep only the last amount",
        "            group[1] += amount",
        "            group[1] = amount",
    ),
)


def line_number(text, needle):
    index = text.find(needle)
    if index < 0:
        raise SystemExit("mutation harness: anchor not found in %s: %r" % (TARGET, needle))
    if text.find(needle, index + 1) >= 0:
        raise SystemExit("mutation harness: anchor is not unique in %s: %r" % (TARGET, needle))
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
