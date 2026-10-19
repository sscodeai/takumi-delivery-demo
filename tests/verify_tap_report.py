#!/usr/bin/env python3
"""REQ-005 verifier: assert the delivered TAP report records a green run.

The requirement document declares (docs/requirements/intake.yaml):

    scenarios:
      - id: SCN-001
        run: "bash run-tests.sh"
        report: tap
        report_path: "reports/tests.tap"

REQ-005 holds the runner to two acceptance criteria: it exits 0 and writes a
readable TAP report, and that report contains no failing test point. The
delivered suite's exit status already reflects its results; this verifier checks
the artifact the document actually names, so a runner that exits 0 while the
report records a failure (or writes a report without a plan or totals) cannot
pass. run-tests.sh invokes it after the delivered suite has written the report
and before the report is echoed as the final stdout stream.

``validate(text)`` is pure text-in / problems-out so the delivered suite can
pin the verifier itself against green, failing and truncated reports; a gate
that cannot fail is not a gate.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "reports", "tests.tap")

PLAN_RE = re.compile(r"^1\.\.(\d+)$", re.M)
TESTS_RE = re.compile(r"^# tests (\d+)$", re.M)
PASS_RE = re.compile(r"^# pass (\d+)$", re.M)
FAIL_RE = re.compile(r"^# fail (\d+)$", re.M)


def validate(text):
    """Return the list of reasons ``text`` is not a green TAP report ([] is good)."""
    problems = []
    if not text.startswith("TAP version 13"):
        problems.append("the report must start with 'TAP version 13'")

    plan = PLAN_RE.search(text)
    if plan is None:
        problems.append("the report must carry a 1..N plan")

    points = [line for line in text.splitlines() if line.startswith(("ok ", "not ok "))]
    not_ok = [line for line in points if line.startswith("not ok ")]
    if not_ok:
        problems.append("%d failing test point(s), first: %s" % (len(not_ok), not_ok[0]))

    tests = TESTS_RE.search(text)
    passes = PASS_RE.search(text)
    fails = FAIL_RE.search(text)
    if tests is None or passes is None or fails is None:
        problems.append("the report must carry '# tests', '# pass' and '# fail' totals")
        return problems

    total = int(tests.group(1))
    passed = int(passes.group(1))
    failed = int(fails.group(1))
    if total != len(points):
        problems.append("the totals say %d test(s) but the report has %d point(s)" % (total, len(points)))
    if plan is not None and int(plan.group(1)) != total:
        problems.append("the plan 1..%s disagrees with the %d test total" % (plan.group(1), total))
    if passed <= 0:
        problems.append("the report records no passing test")
    if failed != 0:
        problems.append("the report records %d failing test(s)" % failed)
    if passed != total:
        problems.append("the report passes %d of %d tests" % (passed, total))
    return problems


def main(argv):
    path = argv[1] if len(argv) > 1 else REPORT
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        sys.stderr.write("verify_tap_report: cannot read %s: %s\n" % (path, error))
        return 1

    problems = validate(text)
    if problems:
        for problem in problems:
            sys.stderr.write("verify_tap_report: %s\n" % problem)
        return 1
    sys.stderr.write("verify_tap_report: %s is a green TAP report\n" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
