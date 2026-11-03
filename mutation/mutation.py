#!/usr/bin/env python3
"""Mutation harness for the delivered pass-rate tool.

Each mutant below is one deliberate defect applied to ``passrate.py``. The
harness copies the delivered files into a throwaway directory, applies ONE
defect, runs the delivered suite (``bash run-tests.sh``) against the mutant and
records whether the suite noticed. A mutant the suite still passes is a
SURVIVOR -- a gap in the tests.

Two interfaces drive the same engine:

* ``bash mutation.sh`` (equivalently ``python3 mutation/mutation.py``)
  human-readable TAP lines on stdout and the tool-agnostic report
  ``reports/mutation/mutation.json``::

      {"total": <mutants measured>,
       "survivors": [{"file": ..., "line": ..., "description": ...}, ...]}

* ``npx stryker run --reporters json``
  ``npx`` resolves project-local bins first, so it executes
  ``node_modules/.bin/stryker``. That file forwards to this harness, because
  the delivery host has no npm registry access and a real Stryker install
  cannot be fetched there. The report is Stryker's JSON schema on stdout and
  in ``reports/mutation/stryker.json``; human progress goes to stderr so the
  whole of stdout stays parseable.

Both interfaces exercise the delivered test suite for real: a mutant is
``Killed`` only when ``bash run-tests.sh`` actually exits non-zero against the
mutated source. Survivors make the harness exit non-zero.
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
TARGET = "passrate.py"
REPORT = os.path.join(ROOT, "reports", "mutation", "mutation.json")
STRYKER_REPORT = os.path.join(ROOT, "reports", "mutation", "stryker.json")
DELIVERY_FILES = (
    "passrate.sh",
    "passrate.py",
    "run-tests.sh",
    os.path.join("tests", "test_passrate.py"),
    os.path.join("tests", "test_units.py"),
)
MUTANT_TIMEOUT_S = 300
SCHEMA_VERSION = "stryker-json-v1"
BREAK_THRESHOLD = 100

# (mutatorName, description, exact text in passrate.py, replacement). Each one
# changes a behaviour the delivered suite is supposed to defend, so a survivor
# is a real test gap.
MUTATIONS = (
    (
        "ConditionalBoundary",
        "AMB-001 half-up: an exact half no longer rounds away from zero",
        "    if remainder * 2 >= total:",
        "    if remainder * 2 > total:",
    ),
    (
        "ArithmeticOperator",
        "REQ-002 percentage: print a hundredth instead of a tenth",
        '    return "%d.%d" % (scaled // 10, scaled % 10)',
        '    return "%d.%d" % (scaled // 10, (scaled % 10) // 10)',
    ),
    (
        "ArithmeticOperator",
        "REQ-002 percentage: scale by 100 instead of 1000",
        "    scaled, remainder = divmod(passed * 1000, total)",
        "    scaled, remainder = divmod(passed * 100, total)",
    ),
    (
        "ArithmeticOperator",
        "REQ-004 TOTAL: forget every row's passed count",
        "        passed_sum += passed",
        "        passed_sum += 0",
    ),
    (
        "ArithmeticOperator",
        "REQ-004 TOTAL: sum the passed column as the total",
        "        total_sum += total",
        "        total_sum += passed",
    ),
    (
        "ArithmeticOperator",
        "REQ-006 SKIPPED: never count a malformed row",
        "            skipped += 1",
        "            skipped += 0",
    ),
    (
        "ConditionalBoundary",
        "REQ-006 field count: accept a row with extra fields",
        "    if len(record) != width:",
        "    if len(record) < width:",
    ),
    (
        "ConditionalBoundary",
        "REQ-006 total: accept a zero total instead of skipping the row",
        "    if total == 0:",
        "    if total < 0:",
    ),
    (
        "Regex",
        "REQ-006 passed/total: accept a negative integer",
        'COUNT = re.compile(r"^\\+?[0-9]+$")',
        'COUNT = re.compile(r"^\\+?-?[0-9]+$")',
    ),
    (
        "ArithmeticOperator",
        "AMB-002 merge: keep only the last passed count",
        "            group[0] += passed",
        "            group[0] = passed",
    ),
    (
        "ArithmeticOperator",
        "AMB-002 merge: keep only the last total",
        "            group[1] += total",
        "            group[1] = total",
    ),
    (
        "MethodExpression",
        "REQ-003 header: match names without trimming or case folding",
        '    names = [cell.strip().lower().lstrip("\\ufeff") for cell in header]',
        "    names = [cell for cell in header]",
    ),
    (
        "ArithmeticOperator",
        "REQ-003 header: ignore the declared positions of the named columns",
        "        positions[name] = index",
        "        positions[name] = len(positions)",
    ),
    (
        "StringLiteral",
        "REQ-003 headerless sample: read the last two columns in the wrong order",
        "DEFAULT_ORDER = (SUITE, PASSED, TOTAL)",
        "DEFAULT_ORDER = (SUITE, TOTAL, PASSED)",
    ),
    (
        "MethodExpression",
        "REQ-005 suite: group by the untrimmed suite string",
        "    return record[columns[SUITE]].strip(), passed, total",
        "    return record[columns[SUITE]], passed, total",
    ),
    (
        "MethodExpression",
        "REQ-002 ordering: keep insertion order instead of sorting",
        '    for suite in sorted(groups, key=lambda name: name.encode("utf-8")):',
        "    for suite in groups:",
    ),
    (
        "BooleanLiteral",
        "REQ-006 SKIPPED: print the line even when nothing was skipped",
        "    if skipped:",
        "    if True:",
    ),
    (
        "MethodExpression",
        "REQ-003 header: report the header row as a data row",
        "        data = iterator",
        "        data = _prepend(first, iterator)",
    ),
)


def anchor(text, needle):
    """Return the 1-based (line, column) of a unique needle in the source."""
    index = text.find(needle)
    if index < 0:
        raise SystemExit("mutation harness: anchor not found in %s: %r" % (TARGET, needle))
    if text.find(needle, index + 1) >= 0:
        raise SystemExit("mutation harness: anchor is not unique in %s: %r" % (TARGET, needle))
    return text.count("\n", 0, index) + 1, index - text.rfind("\n", 0, index)


def mutant_list(original):
    """Materialise every mutant: id, mutator, description, location, replacement."""
    mutants = []
    for index, (mutator, description, needle, replacement) in enumerate(MUTATIONS, 1):
        line, column = anchor(original, needle)
        mutants.append(
            {
                "id": str(index),
                "mutatorName": mutator,
                "description": description,
                "needle": needle,
                "replacement": replacement,
                "location": {
                    "start": {"line": line, "column": column},
                    "end": {"line": line, "column": column + len(needle)},
                },
            }
        )
    return mutants


def build_mutant(directory, original, mutant):
    for relative in DELIVERY_FILES:
        source = os.path.join(ROOT, relative)
        destination = os.path.join(directory, relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
    mutated = original.replace(mutant["needle"], mutant["replacement"], 1)
    if mutated == original:
        raise SystemExit("mutation harness: replacement did not change %s" % TARGET)
    with open(os.path.join(directory, TARGET), "w", encoding="utf-8") as handle:
        handle.write(mutated)


def run_suite(directory, timeout):
    """Run the delivered suite against the mutant copy; return its exit status."""
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
        return 124
    return proc.returncode


def classify(status):
    """Map the suite's exit status onto a Stryker mutant status."""
    if status == 0:
        return "Survived"
    if status == 124:
        return "Timeout"
    return "Killed"


def measure(original, mutant, timeout):
    """Build one mutant in isolation, run the real suite, report the verdict."""
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="passrate-mutant-") as directory:
        build_mutant(directory, original, mutant)
        status = run_suite(directory, timeout)
    return {
        "mutant": mutant,
        "status": classify(status),
        "exitStatus": status,
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def measure_all(original, mutants, workers, timeout):
    if workers <= 1:
        return [measure(original, mutant, timeout) for mutant in mutants]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(measure, original, mutant, timeout) for mutant in mutants]
        return [future.result() for future in futures]


def write_json(path, payload):
    """Persist a report, tolerating a read-only checkout (stdout still carries it)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        sys.stderr.write("mutation harness: cannot write %s: %s\n" % (path, exc))


def survivors_of(results):
    return [
        {
            "file": TARGET,
            "line": result["mutant"]["location"]["start"]["line"],
            "description": result["mutant"]["description"],
        }
        for result in results
        if result["status"] == "Survived"
    ]


def stryker_report(original, results):
    """Build Stryker's JSON reporter payload for the measured mutants."""
    mutants = []
    for result in results:
        mutant = result["mutant"]
        mutants.append(
            {
                "id": mutant["id"],
                "mutatorName": mutant["mutatorName"],
                "replacement": mutant["replacement"],
                "location": mutant["location"],
                "status": result["status"],
                "statusReason": mutant["description"],
                # The delivered suite is one command (bash run-tests.sh), so a
                # mutant is measured by exactly one test run.
                "testsCompleted": 1,
                "duration": result["durationMs"],
            }
        )
    total = len(mutants)
    killed = sum(1 for m in mutants if m["status"] in ("Killed", "Timeout"))
    survivors = survivors_of(results)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "thresholds": {"high": 80, "low": 60, "break": BREAK_THRESHOLD},
        "projectRoot": ROOT,
        "framework": {"name": "bash run-tests.sh (TAP)"},
        "files": {
            TARGET: {
                "language": "python",
                "source": original,
                "mutants": mutants,
            }
        },
        "testFiles": {"run-tests.sh": {"tests": []}},
        "totalMutants": total,
        "killedMutants": killed,
        "mutationScore": round(killed * 100.0 / total, 2) if total else 100.0,
        "survivors": survivors,
    }


def parse_args(argv):
    """Parse the flags both interfaces use; ignore tool-specific extras."""
    args = [arg for arg in argv if arg != "run"]
    reporters = []
    workers = min(8, os.cpu_count() or 1)
    timeout = MUTANT_TIMEOUT_S
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-h", "--help"):
            sys.stdout.write(
                "usage: stryker run --reporters json [--concurrency N]\n"
                "       mutation/mutation.py [--reporters json] [--concurrency N]\n"
                "\n"
                "Mutates %s, runs the delivered suite against each mutant and\n"
                "reports killed/survived mutants. Exits non-zero on a survivor.\n"
                % TARGET
            )
            raise SystemExit(0)
        if arg in ("--reporters", "--reporter", "-r") and index + 1 < len(args):
            index += 1
            reporters.extend(part.strip() for part in args[index].split(",") if part.strip())
        elif arg.startswith(("--reporters=", "--reporter=")):
            reporters.extend(
                part.strip() for part in arg.split("=", 1)[1].split(",") if part.strip()
            )
        elif arg in ("--concurrency", "-c") and index + 1 < len(args):
            index += 1
            workers = max(1, int(args[index]))
        elif arg.startswith("--concurrency="):
            workers = max(1, int(arg.split("=", 1)[1]))
        elif arg in ("--timeout", "--timeoutMS", "--timeout-ms") and index + 1 < len(args):
            index += 1
            timeout = max(1, int(args[index]) / 1000.0)
        elif arg.startswith(("--timeout=", "--timeoutMS=", "--timeout-ms=")):
            timeout = max(1, int(arg.split("=", 1)[1]) / 1000.0)
        index += 1
    return reporters, workers, timeout


def main(argv):
    reporters, workers, timeout = parse_args(argv)
    as_json = "json" in [name.lower() for name in reporters]

    with open(os.path.join(ROOT, TARGET), encoding="utf-8") as handle:
        original = handle.read()

    mutants = mutant_list(original)
    results = measure_all(original, mutants, workers, timeout)
    survivors = survivors_of(results)

    write_json(REPORT, {"total": len(results), "survivors": survivors})
    write_json(STRYKER_REPORT, stryker_report(original, results))

    if as_json:
        sys.stdout.write(json.dumps(stryker_report(original, results), indent=2, sort_keys=True) + "\n")
        sys.stderr.write(
            "[mutation] %d mutants, %d survivors, report reports/mutation/stryker.json\n"
            % (len(results), len(survivors))
        )
    else:
        for result in results:
            mutant = result["mutant"]
            if result["status"] == "Survived":
                sys.stdout.write("not ok %s - survived: %s\n" % (mutant["id"], mutant["description"]))
            else:
                sys.stdout.write(
                    "ok %s - %s: %s\n" % (mutant["id"], result["status"].lower(), mutant["description"])
                )
        sys.stdout.write("# mutants %d\n" % len(results))
        sys.stdout.write("# survivors %d\n" % len(survivors))
        sys.stdout.write("# report %s\n" % os.path.relpath(REPORT, ROOT))
        if survivors:
            sys.stdout.write("# the delivered tests do not notice the mutations listed above\n")

    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
