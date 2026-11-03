#!/usr/bin/env python3
"""TAP integration suite for the delivered ``bash passrate.sh``.

The contract under test is ``docs/requirements/intake.yaml``:

    run:          bash passrate.sh {csv}
    suite line:   <suite> <passed> <total> <pct>
    total line:   TOTAL <passed_sum> <total_sum>
    skipped line: SKIPPED <skipped-count>

The checks here drive the real entry point in subprocesses, so what is asserted
is the behaviour a caller (and the delivery's reviewer) sees. The unit checks
live in ``tests/test_units.py`` and are pulled into the same TAP report. The
report is written to ``reports/tests.tap`` (override with ``TAP_OUT``) and
echoed to stdout; the process exits 0 only when every check passes.
"""

import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_units import UNIT_TESTS  # noqa: E402 - unit checks share this report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "passrate.sh")
TAP_OUT = os.environ.get("TAP_OUT", os.path.join(ROOT, "reports", "tests.tap"))
TIMEOUT = 60

SUITE_LINE = re.compile(r"^(.+) ([0-9]+) ([0-9]+) ([0-9]+\.[0-9])$")
TOTAL_LINE = re.compile(r"^TOTAL ([0-9]+) ([0-9]+)$")
SKIPPED_LINE = re.compile(r"^SKIPPED ([0-9]+)$")

SAMPLE = (
    "auth,48,50\n"
    "billing,17,20\n"
    "search,99,100\n"
    "auth,1,1\n"
    "billing,0,3\n"
)
SAMPLE_HEADERED = "suite,passed,total\n" + SAMPLE
SAMPLE_REPORT = [
    "auth 49 51 96.1",
    "billing 17 23 73.9",
    "search 99 100 99.0",
    "TOTAL 165 174",
]

RESULTS = []
SANDBOX = tempfile.mkdtemp(prefix="passrate-tests-")


def check(name, function):
    """Run one check and record its TAP point."""
    try:
        function()
    except AssertionError as exc:
        RESULTS.append((False, name, str(exc)))
    except Exception as exc:  # noqa: BLE001 - a crashing check is a failing check
        RESULTS.append((False, name, "%s: %s" % (type(exc).__name__, exc)))
    else:
        RESULTS.append((True, name, ""))


def csv_file(text, name="input.csv"):
    path = os.path.join(SANDBOX, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def run(args=None, cwd=None):
    command = ["bash", SCRIPT] + ([] if args is None else list(args))
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def lines_of(output):
    stripped = output.rstrip("\n")
    return stripped.split("\n") if stripped else []


def report(text, name="input.csv"):
    proc = run([csv_file(text, name)])
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert proc.stderr == "", "unexpected stderr %r" % proc.stderr
    return lines_of(proc.stdout)


def expect(text, expected, name="input.csv"):
    got = report(text, name)
    assert got == expected, "got %r, want %r" % (got, expected)


def fail_report(text, name="input.csv"):
    """Run a file that must be a fatal error and return the process."""
    proc = run([csv_file(text, name)])
    assert proc.returncode != 0, "a fatal error must exit non-zero: %r" % proc.stdout
    assert proc.stdout == "", "no report line may be printed: %r" % proc.stdout
    assert proc.stderr.strip(), "a diagnostic on stderr is expected"
    return proc


def split_suite_line(line):
    match = SUITE_LINE.match(line)
    assert match, "not the declared suite-line shape: %r" % line
    return match.group(1), int(match.group(2)), int(match.group(3)), match.group(4)


def suite_lines(lines):
    return [line for line in lines if SUITE_LINE.match(line)]


def independent_percentage(passed, total):
    """Recompute a percentage from counts, half-up, with no delivery code."""
    value = (Decimal(passed) * Decimal(100) / Decimal(total)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    return str(value)


def independent_model(text):
    """An independent pass over the input rows: (suite -> (p, t), skipped, lines)."""
    rows = list(csv.reader(io.StringIO(text)))
    assert rows, "the independent model needs a non-empty file"
    names = [cell.strip().lower() for cell in rows[0]]
    if all(name in names for name in ("suite", "passed", "total")):
        index = {name: names.index(name) for name in ("suite", "passed", "total")}
        data = rows[1:]
        width = len(rows[0])
    else:
        index = {"suite": 0, "passed": 1, "total": 2}
        data = rows
        width = 3

    groups = {}
    skipped = 0
    for row in data:
        if len(row) != width:
            skipped += 1
            continue
        try:
            passed = int(row[index["passed"]].strip())
            total = int(row[index["total"]].strip())
            if passed < 0 or total <= 0 or not row[index["passed"]].strip().isdigit():
                skipped += 1
                continue
        except ValueError:
            skipped += 1
            continue
        suite = row[index["suite"]].strip()
        old = groups.get(suite, (0, 0))
        groups[suite] = (old[0] + passed, old[1] + total)

    lines = []
    for suite in sorted(groups, key=lambda name: name.encode("utf-8")):
        passed, total = groups[suite]
        lines.append(
            "%s %d %d %s" % (suite, passed, total, independent_percentage(passed, total))
        )
    lines.append(
        "TOTAL %d %d"
        % (sum(p for p, _t in groups.values()), sum(t for _p, t in groups.values()))
    )
    if skipped:
        lines.append("SKIPPED %d" % skipped)
    return groups, skipped, lines


# --- REQ-001: the CLI entry point --------------------------------------------


def req_001_declared_sample_report_is_exact():
    expect(SAMPLE, SAMPLE_REPORT)


def req_001_exits_zero_and_writes_nothing_to_stderr():
    proc = run([csv_file(SAMPLE)])
    assert proc.returncode == 0, "exit %d" % proc.returncode
    assert proc.stderr == "", "unexpected stderr %r" % proc.stderr
    assert proc.stdout.endswith("\n"), "the report ends with a newline"


def req_001_missing_input_path_is_a_fatal_error():
    proc = run([os.path.join(SANDBOX, "does-not-exist.csv")])
    assert proc.returncode != 0, "a missing path must exit non-zero"
    assert proc.stdout == "", "no report line for a missing path"
    assert proc.stderr.strip(), "a diagnostic on stderr is expected"


def req_001_an_unreadable_path_is_a_fatal_error():
    directory = os.path.join(SANDBOX, "a-directory")
    os.makedirs(directory, exist_ok=True)
    proc = run([directory])
    assert proc.returncode != 0, "a directory is not a readable CSV"
    assert proc.stdout == "", "no report line for an unreadable path"
    assert proc.stderr.strip(), "a diagnostic on stderr is expected"


def req_001_no_argument_is_a_usage_error():
    proc = run([])
    assert proc.returncode != 0, "the path is required"
    assert proc.stdout == ""
    assert proc.stderr.strip()


def req_001_entry_point_sits_at_the_repository_root():
    assert os.path.isfile(SCRIPT), "passrate.sh must exist at the repository root"
    assert os.path.dirname(SCRIPT) == ROOT, SCRIPT


def req_001_reads_the_path_substituted_as_the_first_argument():
    # A judge replaces {csv} with its own fixture path and may invoke the
    # script from any working directory. Only $1 names the fixture.
    path = csv_file(SAMPLE, "judge-fixture.csv")
    proc = run([path], cwd=SANDBOX)
    assert proc.returncode == 0, "exit %d, stderr %r" % (proc.returncode, proc.stderr)
    assert lines_of(proc.stdout) == SAMPLE_REPORT, proc.stdout


def req_001_stdout_carries_only_declared_shapes():
    text = (
        "suite,passed,total\n"
        "alpha,7,9\n"
        "beta,1,16\n"
        "alpha,1,2\n"
        "gamma,0,0\n"
        "delta,3,7\n"
    )
    lines = report(text)
    assert lines, "a report is expected"
    totals = 0
    skipped = 0
    suite_seen = 0
    for position, line in enumerate(lines):
        if TOTAL_LINE.match(line):
            totals += 1
            assert position >= suite_seen, "TOTAL must follow the suite lines"
        elif SKIPPED_LINE.match(line):
            skipped += 1
            assert position == len(lines) - 1, "SKIPPED must be the final line"
        else:
            assert SUITE_LINE.match(line), "undeclared line shape: %r" % line
            suite_seen += 1
    assert totals == 1, "exactly one TOTAL line, got %d" % totals
    assert skipped == 1, "one skipped row, got SKIPPED %d" % skipped


# --- REQ-002: one line per suite, percentage to one decimal ------------------


def req_002_percentage_has_exactly_one_fractional_digit():
    lines = report("suite,passed,total\na,48,50\nb,17,20\nc,5,5\nd,0,3\n")
    assert lines[0] == "a 48 50 96.0", lines[0]
    assert lines[1] == "b 17 20 85.0", lines[1]
    assert lines[2] == "c 5 5 100.0", lines[2]
    assert lines[3] == "d 0 3 0.0", lines[3]


def req_002_percentage_is_derived_from_the_printed_counts():
    text = (
        "suite,passed,total\n"
        "alpha,7,9\n"
        "beta,1,16\n"
        "alpha,1,2\n"
        "delta,3,7\n"
    )
    for line in suite_lines(report(text)):
        suite, passed, total, pct = split_suite_line(line)
        assert pct == independent_percentage(passed, total), (
            "%r: printed %s, recomputed %s"
            % (line, pct, independent_percentage(passed, total))
        )


# --- REQ-003: columns located by header name --------------------------------


def req_003_reordered_header_yields_the_sample_report():
    text = (
        "total,suite,passed\n"
        "50,auth,48\n"
        "20,billing,17\n"
        "100,search,99\n"
        "1,auth,1\n"
        "3,billing,0\n"
    )
    expect(text, SAMPLE_REPORT)


def req_003_extra_columns_are_ignored():
    text = (
        "id,suite,note,total,passed\n"
        "1,alpha,first,10,9\n"
        "2,beta,second,20,17\n"
    )
    expect(
        text,
        ["alpha 9 10 90.0", "beta 17 20 85.0", "TOTAL 26 30"],
    )


def req_003_header_names_are_trimmed_and_case_insensitive():
    text = " Suite , PASSED , TOTAL \nauth,48,50\n"
    expect(text, ["auth 48 50 96.0", "TOTAL 48 50"])


def req_003_the_header_row_is_never_reported():
    lines = report("suite,passed,total\nauth,48,50\n", "header-row.csv")
    suites = [split_suite_line(line)[0] for line in suite_lines(lines)]
    assert suites == ["auth"], "the header must not become a suite: %r" % suites


def req_003_a_missing_column_is_fatal_and_named():
    cases = (
        ("passed,total\nauth,1,2\n", "suite"),
        ("suite,total\nauth,1,2\n", "passed"),
        ("suite,passed\nauth,1,2\n", "total"),
    )
    for text, missing in cases:
        proc = fail_report(text, "missing-%s.csv" % missing)
        assert missing in proc.stderr, "%r not named in %r" % (missing, proc.stderr)


def req_003_a_headerless_sample_and_a_headered_sample_agree():
    assert report(SAMPLE, "plain.csv") == report(SAMPLE_HEADERED, "headered.csv")


# --- REQ-004: one totals line ------------------------------------------------


def req_004_declared_sample_totals_are_165_and_174():
    assert report(SAMPLE)[-1] == "TOTAL 165 174"


def req_004_totals_line_is_printed_once_and_last_of_the_aggregates():
    lines = report(SAMPLE)
    totals = [line for line in lines if TOTAL_LINE.match(line)]
    assert totals == ["TOTAL 165 174"], totals
    assert lines[-1] == "TOTAL 165 174", lines


def req_004_a_single_suite_still_prints_totals():
    expect("suite,passed,total\nonly,2,3\n", ["only 2 3 66.7", "TOTAL 2 3"])


def req_004_totals_follow_the_suite_lines_even_when_rows_were_skipped():
    lines = report(
        "suite,passed,total\n"
        "alpha,1,2\n"
        "broken,oops,5\n"
        "beta,3,4\n"
    )
    assert lines == [
        "alpha 1 2 50.0",
        "beta 3 4 75.0",
        "TOTAL 4 6",
        "SKIPPED 1",
    ], lines


# --- REQ-005: repeated suites merge ------------------------------------------


def req_005_repeated_suite_rows_merge_into_one_line():
    lines = report("suite,passed,total\nauth,48,50\nauth,1,1\n")
    assert lines == ["auth 49 51 96.1", "TOTAL 49 51"], lines


def req_005_line_count_is_distinct_suites_not_rows():
    text = "suite,passed,total\na,1,2\na,1,2\nb,1,2\nb,1,2\nb,1,2\nc,1,2\n"
    lines = report(text)
    assert len(suite_lines(lines)) == 3, lines
    assert lines[:3] == ["a 2 4 50.0", "b 3 6 50.0", "c 1 2 50.0"], lines


def req_005_merge_uses_valid_rows_only_for_a_repeated_suite():
    lines = report("suite,passed,total\nauth,48,50\nauth,1,1\nauth,nope,9\n")
    assert lines == ["auth 49 51 96.1", "TOTAL 49 51", "SKIPPED 1"], lines


# --- REQ-006: malformed rows are skipped and counted -------------------------


def req_006_an_unparsable_passed_is_skipped_and_counted():
    lines = report("suite,passed,total\nbroken,oops,10\n")
    assert not suite_lines(lines), "no suite line from an unusable row: %r" % lines
    assert lines == ["TOTAL 0 0", "SKIPPED 1"], lines


def req_006_a_clean_input_prints_no_skipped_line():
    lines = report(SAMPLE)
    assert not any(line.startswith("SKIPPED") for line in lines), lines


def req_006_skipped_rows_are_excluded_from_the_totals():
    lines = report(
        "suite,passed,total\n"
        "good,4,5\n"
        "bad,x,9\n"
        "zero,3,0\n"
        "negative,-1,4\n"
        "fraction,1.5,4\n"
        "short,1\n"
    )
    assert lines == ["good 4 5 80.0", "TOTAL 4 5", "SKIPPED 5"], lines


def req_006_a_zero_total_suite_gets_no_line_and_is_skipped():
    lines = report("suite,passed,total\nzero,0,0\n")
    assert lines == ["TOTAL 0 0", "SKIPPED 1"], lines


def req_006_a_skipped_row_does_not_remove_a_valid_row_of_the_same_suite():
    lines = report("suite,passed,total\nauth,1,2\nauth,nope,9\n")
    assert lines == ["auth 1 2 50.0", "TOTAL 1 2", "SKIPPED 1"], lines


# --- AMB-001: half-up rounding ----------------------------------------------


def amb_001_an_exact_half_rounds_away_from_zero():
    lines = report("suite,passed,total\nhalf,1,16\nupper,3,16\n")
    assert lines[0] == "half 1 16 6.3", lines
    assert lines[1] == "upper 3 16 18.8", lines


def amb_001_a_stored_half_at_two_decimals_rounds_up():
    # 1921/2000 = 96.05% -> 96.1
    lines = report("suite,passed,total\nalmost,1921,2000\n")
    assert lines[0] == "almost 1921 2000 96.1", lines


def amb_001_a_value_just_below_a_half_rounds_down():
    # 2401/2500 = 96.04% -> 96.0
    lines = report("suite,passed,total\nbelow,2401,2500\n")
    assert lines[0] == "below 2401 2500 96.0", lines


def amb_001_a_half_below_one_percent_rounds_up_to_one_decimal():
    # 1/2000 = 0.05% -> 0.1 (truncate would print 0.0)
    lines = report("suite,passed,total\ntiny,1,2000\n")
    assert lines[0] == "tiny 1 2000 0.1", lines


# --- AMB-002 / AMB-003 -------------------------------------------------------


def amb_002_merge_sums_both_counts_and_rows():
    lines = report(
        "suite,passed,total\n"
        "merge,48,50\n"
        "merge,1,1\n"
        "merge,0,3\n"
    )
    assert lines == ["merge 49 54 90.7", "TOTAL 49 54"], lines


def amb_003_skip_count_counts_each_unusable_row_once():
    lines = report(
        "suite,passed,total\n"
        "a,1,2\n"
        "a,1\n"
        "b,2,x\n"
        "c,-3,4\n"
        "d,0,0\n"
    )
    assert lines == ["a 1 2 50.0", "TOTAL 1 2", "SKIPPED 4"], lines


def amb_003_every_unusable_row_shape_is_skipped_and_counted():
    # The AMB-003 answer lists each malformed shape; every one of them must
    # produce no suite line, contribute nothing to TOTAL, and be counted once.
    cases = {
        "too-few-fields": "broken,1\n",
        "too-many-fields": "broken,1,2,extra\n",
        "non-integer-passed": "broken,x,2\n",
        "non-integer-total": "broken,1,x\n",
        "negative-passed": "broken,-1,2\n",
        "negative-total": "broken,1,-2\n",
        "zero-total": "broken,0,0\n",
        "blank-passed": "broken,,2\n",
    }
    for name, row in cases.items():
        lines = report("suite,passed,total\n" + row, "%s.csv" % name)
        assert lines == ["TOTAL 0 0", "SKIPPED 1"], (name, lines)


# --- REL-001 / DIFF-001: independent recomputation ---------------------------


def rel_001_every_percentage_matches_its_own_printed_counts():
    text = (
        "total,id,suite,passed\n"
        "11,1,alpha,7\n"
        "9,2,alpha,1\n"
        "16,3,beta,1\n"
        "7,4,delta,3\n"
        "3,5,gamma,0\n"
    )
    for line in suite_lines(report(text)):
        _suite, passed, total, pct = split_suite_line(line)
        assert pct == independent_percentage(passed, total)


def diff_001_an_independent_pass_yields_the_same_lines():
    text = (
        "suite,passed,total\n"
        "alpha,7,9\n"
        "beta,1,16\n"
        "alpha,1,2\n"
        "gamma,0,0\n"
        "delta,3,7\n"
        "broken,oops,4\n"
    )
    _groups, _skipped, expected = independent_model(text)
    assert report(text) == expected


def diff_001_totals_are_the_sum_of_the_counted_rows():
    text = "suite,passed,total\nx,3,4\ny,1,6\nx,2,5\nz,0,0\n"
    lines = report(text)
    counted = [split_suite_line(line) for line in suite_lines(lines)]
    total = TOTAL_LINE.match(lines[-2])
    assert total, lines
    assert int(total.group(1)) == sum(item[1] for item in counted)
    assert int(total.group(2)) == sum(item[2] for item in counted)


# --- extra robustness --------------------------------------------------------


def extra_crlf_input_is_read_correctly():
    text = "suite,passed,total\r\nauth,48,50\r\nbilling,17,20\r\n"
    expect(text, ["auth 48 50 96.0", "billing 17 20 85.0", "TOTAL 65 70"])


def extra_a_quoted_suite_containing_a_comma_stays_one_line():
    lines = report('suite,passed,total\n"auth,eu",1,2\n')
    assert lines == ["auth,eu 1 2 50.0", "TOTAL 1 2"], lines


def extra_an_empty_file_is_a_fatal_error():
    proc = fail_report("", "empty.csv")
    assert "empty" in proc.stderr.lower() or "header" in proc.stderr.lower(), proc.stderr


def extra_a_utf8_bom_header_is_accepted():
    text = "\ufeffsuite,passed,total\nauth,1,2\n"
    expect(text, ["auth 1 2 50.0", "TOTAL 1 2"])


def extra_report_order_is_sorted_by_suite_name():
    lines = report("suite,passed,total\nzeta,1,2\nalpha,1,2\nmid,1,2\n")
    assert [split_suite_line(line)[0] for line in suite_lines(lines)] == [
        "alpha",
        "mid",
        "zeta",
    ]


def extra_passed_above_total_is_counted():
    lines = report("suite,passed,total\nodd,3,2\n")
    assert lines == ["odd 3 2 150.0", "TOTAL 3 2"], lines


TESTS = [
    (name, value)
    for name, value in sorted(globals().items())
    if (
        name.startswith(("req_", "amb_", "rel_", "diff_", "extra_"))
        and callable(value)
    )
] + UNIT_TESTS


def emit_tap():
    lines = ["TAP version 13", "1..%d" % len(RESULTS)]
    passed = failed = 0
    for index, (ok, name, detail) in enumerate(RESULTS, 1):
        if ok:
            passed += 1
            lines.append("ok %d - %s" % (index, name))
        else:
            failed += 1
            lines.append("not ok %d - %s" % (index, name))
            for part in (detail or "assertion failed").splitlines():
                lines.append("# %s" % part)
    lines.append("# tests %d" % len(RESULTS))
    lines.append("# pass %d" % passed)
    lines.append("# fail %d" % failed)
    text = "\n".join(lines) + "\n"
    directory = os.path.dirname(TAP_OUT)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(TAP_OUT, "w", encoding="utf-8") as handle:
        handle.write(text)
    sys.stdout.write(text)
    return 1 if failed else 0


def main():
    try:
        for name, function in TESTS:
            check(name, function)
        return emit_tap()
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
