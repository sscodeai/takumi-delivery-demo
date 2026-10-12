#!/usr/bin/env python3
"""Mutation testing for the delivered CLI tool (REL-005, mutation-detection).

The requirement document declares that "the delivered tests fail when the
delivered aggregation behaviour is mutated". This harness is the tool behind
that relation: it copies the project, applies one deliberate defect to
``summary.sh`` at a time, runs the delivered test suite against the mutant and
counts a mutant as *killed* when the suite fails.

A mutant the suite does not catch *survives*. The confirmed requirement allows
zero survivors (``mutation.max_survivors: 0``), so any survivor is a real gap in
the delivered tests and is reported in ``reports/mutation.json`` in the declared
``survivors-json`` shape:

    {"total": <int>, "survivors": [{"file", "line", "description"}, ...]}

The runner never mutates the working copy: every mutant is applied inside a
throwaway copy under the system temp directory, so a crash cannot leave the
delivered tree in a mutant state.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUMMARY = os.path.join(ROOT, "summary.sh")
REPORT = os.path.join(ROOT, "reports", "mutation.json")

# The delivered tests that drive summary.sh through its process boundary. The
# service tests are excluded on purpose: this relation is about the aggregation
# behaviour of the CLI deliverable, which these modules fully exercise.
CLI_TEST_MODULES = [
    "test_aggregates",
    "test_decisions",
    "test_entrypoint",
    "test_malformed",
    "test_nonfunctional",
    "test_parsing",
    "test_properties",
    "test_reference",
]

# Copy exclusions: VCS metadata, tool state, generated reports and caches are
# not part of the behaviour under test.
COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".takumi", "reports", "__pycache__", "node_modules", ".pytest_cache"
)

# One focused defect per confirmed decision and per parsing rule. Each anchor is
# a single line of summary.sh; the mutation replaces it with a plausible wrong
# implementation that must make the delivered suite fail.
MUTATIONS = [
    {
        "id": "rounding-boundary",
        "description": "round an exact half toward zero instead of away from zero",
        "old": "if remainder * 2 >= denominator:",
        "new": "if remainder * 2 > denominator:",
    },
    {
        "id": "station-order",
        "description": "emit station lines in descending instead of ascending id order",
        "old": 'sorted(stations, key=lambda name: name.encode("utf-8"))',
        "new": "sorted(stations, reverse=True)",
    },
    {
        "id": "field-count",
        "description": "accept rows with more than three fields instead of skipping them",
        "old": "if len(row) != 3:",
        "new": "if len(row) < 3:",
    },
    {
        "id": "skipped-report",
        "description": "report a skipped count of zero instead of the real count",
        "old": 'out.append("SKIPPED %d" % skipped)',
        "new": 'out.append("SKIPPED %d" % 0)',
    },
    {
        "id": "total-report",
        "description": "report the skipped count on the TOTAL line instead of the accepted count",
        "old": 'out.append("TOTAL %d" % total)',
        "new": 'out.append("TOTAL %d" % skipped)',
    },
    {
        "id": "empty-station",
        "description": "aggregate an empty station id instead of skipping the row",
        "old": 'if station == "":',
        "new": "if False:",
    },
    {
        "id": "date-validation",
        "description": "accept any date field instead of validating the calendar date",
        "old": "if not is_date(row[date_i]):",
        "new": "if False:",
    },
    {
        "id": "header-consumption",
        "description": "treat the declared header row as a reading instead of consuming it",
        "old": "if all(name in names for name in HEADER_NAMES):",
        "new": "if False:",
    },
    {
        "id": "maximum-tracking",
        "description": "update the maximum on a smaller reading instead of a larger one",
        "old": "if temperature > entry[2]:",
        "new": "if temperature < entry[2]:",
    },
    {
        "id": "mean-denominator",
        "description": "divide the mean by one reading too many",
        "old": "render_mean(accumulated, count),",
        "new": "render_mean(accumulated, count + 1),",
    },
    {
        "id": "duplicate-count",
        "description": "count a repeated reading only once in the station count",
        "old": "entry[0] += 1",
        "new": "entry[0] += 0",
    },
]

# A single mutant whose tests hang is still caught by the suite's own timeout;
# the bound here only stops a pathological mutant from stalling the run.
MUTANT_TIMEOUT_S = 180


def line_of(content, needle):
    return content[: content.index(needle)].count("\n") + 1


def run_tests(worktree):
    """Run the delivered CLI suite in the copied project; True when it passes."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", *CLI_TEST_MODULES],
            cwd=os.path.join(worktree, "tests"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=MUTANT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        # A mutant that hangs the suite did not survive: the suite did not pass.
        return False
    return result.returncode == 0


def main():
    with open(SUMMARY, "r", encoding="utf-8") as handle:
        pristine = handle.read()

    work = tempfile.mkdtemp(prefix="takumi-mutation-")
    survivors = []
    total = 0
    try:
        shutil.copytree(ROOT, work, dirs_exist_ok=True, ignore=COPY_IGNORE)
        summary_copy = os.path.join(work, "summary.sh")
        for mutation in MUTATIONS:
            total += 1
            old = mutation["old"]
            if pristine.count(old) != 1:
                # An anchor that no longer exists cannot be applied; that is not
                # a pass, it is the harness losing its grip on the deliverable.
                survivors.append(
                    {
                        "file": "summary.sh",
                        "line": 1,
                        "description": "%s: mutation anchor not found exactly once"
                        % mutation["description"],
                    }
                )
                print("mutant %-20s SURVIVED (anchor missing)" % mutation["id"])
                continue
            with open(summary_copy, "w", encoding="utf-8") as handle:
                handle.write(pristine.replace(old, mutation["new"], 1))
            passed = run_tests(work)
            state = "SURVIVED" if passed else "killed"
            print("mutant %-20s %s" % (mutation["id"], state))
            if passed:
                survivors.append(
                    {
                        "file": "summary.sh",
                        "line": line_of(pristine, old),
                        "description": mutation["description"],
                    }
                )
        # Restore the pristine source in the copy so a later reader never sees a
        # mutant (the copy is removed anyway, but the intent is explicit).
        with open(summary_copy, "w", encoding="utf-8") as handle:
            handle.write(pristine)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump({"total": total, "survivors": survivors}, handle, indent=2)
        handle.write("\n")

    print("MUTATION: %d mutant(s), %d survivor(s)" % (total, len(survivors)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
