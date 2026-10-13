#!/usr/bin/env python3
"""Mutation harness behind the declared `npx stryker run --reporters json`.

The confirmed requirement document declares (docs/requirements/intake.yaml):

    mutation:
      run:           npx stryker run --reporters json
      report_path:   reports/mutation/mutation.json
      format:        survivors-json
      max_survivors: 0
      timeoutMs:     900000

For every mutant below the harness copies the project into a throwaway
directory, applies the single deliberate defect to common_keys.py, and runs the
delivered test suite (``bash run-tests.sh``) against the mutant. A mutant the
suite still passes is a SURVIVOR: the tests did not notice the behaviour change.
The document holds the delivered suite to zero survivors, so this command exits
non-zero when any mutant survives and writes the survivors-json report either
way.

The harness fails closed: a mutant pattern that no longer matches the source is
an error, not a silent pass, so a rename cannot make the gate vacuous. A control
run on an unmutated copy must pass first; otherwise every mutant would look
"killed" for a reason unrelated to its defect and the gate would measure
nothing.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = "common_keys.py"
DEFAULT_REPORT = os.path.join("reports", "mutation", "mutation.json")
SUITE_TIMEOUT_S = 300

# (id, find, replace, description). Every entry names a defect a delivered test
# is expected to catch; the descriptions are what the survivors-json report
# carries, matching the declared survivor shape {file, line, description}.
MUTANTS = [
    (
        "m01-union-not-intersection",
        "        shared &= set(element.keys())",
        "        shared |= set(element.keys())",
        "the key sets are unioned instead of intersected",
    ),
    (
        "m02-reversed-order",
        "    return sorted(shared)",
        "    return sorted(shared, reverse=True)",
        "the common keys are printed in descending order",
    ),
    (
        "m03-case-insensitive-order",
        "    return sorted(shared)",
        "    return sorted(shared, key=str.lower)",
        "the common keys are ordered case-insensitively",
    ),
    (
        "m04-length-order",
        "    return sorted(shared)",
        "    return sorted(shared, key=len)",
        "the common keys are ordered by length, not by code point",
    ),
    (
        "m05-empty-array-error",
        "    if not objects:\n        return []",
        "    if not objects:\n        raise InputError(\"the array holds no objects\")",
        "an array with no objects is rejected instead of printing none",
    ),
    (
        "m06-non-array-accepted",
        "    if not isinstance(value, list):",
        "    if False:",
        "a top-level value that is not an array is not rejected",
    ),
    (
        "m07-non-object-accepted",
        "        if not isinstance(element, dict):",
        "        if False:",
        "an array element that is not an object is not rejected",
    ),
    (
        "m08-object-element-rejected",
        "        if not isinstance(element, dict):",
        "        if isinstance(element, dict):",
        "an object element is rejected as if it were not one",
    ),
    (
        "m09-none-uppercase",
        '        sys.stdout.write("none\\n")',
        '        sys.stdout.write("NONE\\n")',
        "the none word is no longer lowercase",
    ),
    (
        "m10-none-missing-newline",
        '        sys.stdout.write("none\\n")',
        '        sys.stdout.write("none")',
        "the none word loses its trailing newline",
    ),
    (
        "m11-key-label",
        '        sys.stdout.write("".join(key + "\\n" for key in keys))',
        '        sys.stdout.write("".join("key: " + key + "\\n" for key in keys))',
        "each common key gains a label",
    ),
    (
        "m12-key-crlf",
        '        sys.stdout.write("".join(key + "\\n" for key in keys))',
        '        sys.stdout.write("".join(key + "\\r\\n" for key in keys))',
        "each common key line ends with CRLF instead of LF",
    ),
    (
        "m13-always-none",
        "    if keys:",
        "    if False:",
        "a shared key list is replaced by none",
    ),
    (
        "m14-never-none",
        "    if keys:",
        "    if True:",
        "the none case prints an empty line instead of the word none",
    ),
    (
        "m15-usage-success",
        "        sys.stderr.write(USAGE)\n        return 2",
        "        sys.stderr.write(USAGE)\n        return 0",
        "a missing argument is reported as success",
    ),
    (
        "m16-usage-inverted",
        "    if len(argv) != 2:",
        "    if len(argv) == 2:",
        "the argument-count gate is inverted",
    ),
    (
        "m17-unreadable-success",
        '        sys.stderr.write("%s: cannot read %s: %s\\n" % (PREFIX, path, error))\n        return 1',
        '        sys.stderr.write("%s: cannot read %s: %s\\n" % (PREFIX, path, error))\n        return 0',
        "an unreadable file is reported as success",
    ),
    (
        "m18-malformed-success",
        '        sys.stderr.write("%s: %s: %s\\n" % (PREFIX, path, error))\n        return 1',
        '        sys.stderr.write("%s: %s: %s\\n" % (PREFIX, path, error))\n        return 0',
        "a malformed input is reported as success",
    ),
    (
        "m19-start-from-last",
        "    shared = set(objects[0].keys())",
        "    shared = set(objects[-1].keys())",
        "the intersection starts from the last object instead of the first",
    ),
    (
        "m20-skip-first-object",
        "    for element in objects[1:]:",
        "    for element in objects[2:]:",
        "the first object is never intersected",
    ),
    (
        "m21-empty-start-set",
        "    shared = set(objects[0].keys())",
        "    shared = set()",
        "the intersection starts empty, so nothing is ever common",
    ),
    (
        "m22-values-instead-of-keys",
        "        shared &= set(element.keys())",
        "        shared &= set(element.values())",
        "the intersection uses values instead of keys",
    ),
]

# The copy must be a working project, so only VCS metadata, previous reports and
# bytecode caches are left out.
IGNORED = shutil.ignore_patterns(".git", "reports", "__pycache__", "*.pyc")


def line_of(content, index):
    return content.count("\n", 0, index) + 1


def run_suite(directory):
    """Return True when the delivered suite passes in the copied project."""
    try:
        result = subprocess.run(
            ["bash", "run-tests.sh"],
            cwd=directory,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=SUITE_TIMEOUT_S,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def copy_project():
    """Copy the project into a fresh throwaway directory and return its path."""
    directory = tempfile.mkdtemp(prefix="common-keys-mutation-")
    shutil.copytree(ROOT, directory, dirs_exist_ok=True, ignore=IGNORED)
    return directory


def run(report_path):
    original_source = open(os.path.join(ROOT, TARGET), encoding="utf-8").read()
    survivors = []
    total = 0

    # Control run: the delivered suite must pass on an unmutated copy. If it
    # does not, every mutant below would be reported as killed for a reason
    # unrelated to the defect, so the gate would measure nothing. Fail closed.
    control = copy_project()
    try:
        if not run_suite(control):
            raise SystemExit(
                "mutation harness: the delivered suite fails on an unmutated copy, "
                "so every mutant would be reported as killed; the mutation report "
                "would be vacuous"
            )
    finally:
        shutil.rmtree(control, ignore_errors=True)
    sys.stderr.write("control  the delivered suite passes on an unmutated copy\n")

    for mutant_id, find, replace, description in MUTANTS:
        total += 1
        index = original_source.find(find)
        if index == -1:
            raise SystemExit(
                "mutation harness: mutant %s does not match %s; the harness would be vacuous"
                % (mutant_id, TARGET)
            )
        work_directory = copy_project()
        try:
            target = os.path.join(work_directory, TARGET)
            mutated = original_source[:index] + replace + original_source[index + len(find):]
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(mutated)

            if run_suite(work_directory):
                survivors.append(
                    {
                        "file": TARGET,
                        "line": line_of(original_source, index),
                        "description": description,
                    }
                )
                sys.stderr.write("SURVIVED %s (%s) %s\n" % (mutant_id, TARGET, description))
            else:
                sys.stderr.write("killed   %s (%s)\n" % (mutant_id, TARGET))
        finally:
            shutil.rmtree(work_directory, ignore_errors=True)

    report = {"total": total, "survivors": survivors}
    absolute = report_path if os.path.isabs(report_path) else os.path.join(ROOT, report_path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    sys.stderr.write("%d mutant(s), %d survivor(s)\n" % (total, len(survivors)))
    return 1 if survivors else 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    arguments, _ = parser.parse_known_args(argv)
    return run(arguments.report)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
