#!/usr/bin/env python3
"""Mutation testing for the delivered summary.sh CLI (REQ-005).

The confirmed requirement document declares:

    mutation:
      run: "bash mutation-test.sh"
      report_path: "reports/mutation/mutation.json"
      format: survivors-json
      max_survivors: 0

This is the tool behind that contract. It never mutates the working copy: it
copies the project into a throwaway directory, applies ONE deliberate defect to
``summary.sh`` at a time, and runs the delivered CLI test suite against the
mutant. A mutant is *killed* when the suite fails; a mutant the suite still
passes is a *survivor* and is reported.

The requirement allows zero survivors, so every entry in MUTATIONS has to be
caught by a delivered test. Each mutation anchors on an exact substring of
``summary.sh``; an anchor that no longer occurs exactly once is reported as a
survivor, so the harness fails closed when the source drifts instead of
silently skipping a mutant.

The report is written in the declared ``survivors-json`` shape:

    {"total": <int>, "survivors": [{"file": ..., "line": <int>,
                                    "description": ...}, ...]}
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
REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")

# Test modules that drive summary.sh through its process boundary. The two
# service modules exercise the separate HTTP artifact (station_summary.py),
# which none of these mutations touch, and the mutation-harness module only
# inspects this file, so none of them can kill a summary.sh mutant; running
# them would only spend the mutation budget. Everything else is discovered.
EXCLUDED_MODULES = frozenset(
    {
        "test_service",
        "test_service_units",
        "test_mutation_harness",
    }
)

# Copy exclusions: VCS metadata, engine state, generated reports and caches are
# not part of the behaviour under test.
COPY_IGNORE = shutil.ignore_patterns(
    ".git", ".takumi", "reports", "__pycache__", "node_modules", ".pytest_cache"
)

# One focused defect per parsing rule, aggregate and confirmed decision. Every
# anchor occurs exactly once in summary.sh today; the harness reports a missing
# or ambiguous anchor as a survivor rather than skipping it.
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
        "description": "report the skipped count on the TOTAL line instead of the valid count",
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
        "id": "temperature-validation",
        "description": "accept a non-numeric temperature instead of skipping the row",
        "old": "if not is_temperature(row[temperature_i]):",
        "new": "if False:",
    },
    {
        "id": "header-consumption",
        "description": "treat the declared header row as a reading instead of consuming it",
        "old": "if all(name in names for name in HEADER_NAMES):",
        "new": "if False:",
    },
    {
        "id": "minimum-tracking",
        "description": "update the minimum on a larger reading instead of a smaller one",
        "old": "if value < entry[1]:",
        "new": "if value > entry[1]:",
    },
    {
        "id": "maximum-tracking",
        "description": "update the maximum on a smaller reading instead of a larger one",
        "old": "if value > entry[2]:",
        "new": "if value < entry[2]:",
    },
    {
        "id": "sum-accumulation",
        "description": "subtract a reading from the running sum instead of adding it",
        "old": "entry[3] += value",
        "new": "entry[3] -= value",
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

# A mutant whose tests hang is still caught by the suite's own timeout; this
# bound only stops a pathological mutant from stalling the whole run. The
# declared mutation bound is 900s for the whole harness.
MUTANT_TIMEOUT_S = 240


def line_of(content, needle):
    """The 1-based line number of the first occurrence of ``needle``."""
    return content[: content.index(needle)].count("\n") + 1


def cli_test_modules(tests_dir):
    """The delivered test modules that exercise the CLI, in name order."""
    modules = []
    for name in sorted(os.listdir(tests_dir)):
        if not name.startswith("test_") or not name.endswith(".py"):
            continue
        module = name[: -len(".py")]
        if module in EXCLUDED_MODULES:
            continue
        modules.append(module)
    return modules


def write_report(path, total, survivors):
    """Write the declared survivors-json report and return the path."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"total": total, "survivors": survivors}, handle, indent=2)
        handle.write("\n")
    return path


def run_tests(worktree):
    """Run the delivered CLI suite in the copied project; True when it passes."""
    tests_dir = os.path.join(worktree, "tests")
    modules = cli_test_modules(tests_dir)
    if not modules:
        # A suite with nothing to run cannot kill a mutant: fail closed.
        return False
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", *modules],
            cwd=tests_dir,
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
                print("mutant %-22s SURVIVED (anchor missing)" % mutation["id"])
                continue
            with open(summary_copy, "w", encoding="utf-8") as handle:
                handle.write(pristine.replace(old, mutation["new"], 1))
            passed = run_tests(work)
            state = "SURVIVED" if passed else "killed"
            print("mutant %-22s %s" % (mutation["id"], state))
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

    write_report(REPORT, total, survivors)
    print("MUTATION: %d mutant(s), %d survivor(s)" % (total, len(survivors)))
    return 0 if not survivors else 1


if __name__ == "__main__":
    sys.exit(main())
