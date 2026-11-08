#!/usr/bin/env python3
"""TAP suite for the delivered ``bash ticket-summary.sh``.

The contract under test is ``docs/requirements/intake.yaml``:

    run:           bash ticket-summary.sh {csv}
    assignee line: <assignee> <open> <closed>
    total line:    TOTAL <open-sum> <closed-sum>

Every check drives the real entry point in a subprocess, so what is asserted is
behaviour a caller sees.  The report is written to ``reports/tests.tap``
(override with ``TAP_OUT``) and echoed to stdout; the process exits 0 only when
every check passes.

Check names carry the criterion they defend (``req00n_...``) and, for the
document's open questions, the decision they pin (``amb00n_...``), so the TAP
report shows which reading was adopted.
"""

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "ticket-summary.sh")
TAP_OUT = os.environ.get("TAP_OUT", os.path.join(ROOT, "reports", "tests.tap"))
TIMEOUT = 30

ASSIGNEE_LINE = re.compile(r"^(\S.*) ([0-9]+) ([0-9]+)$")
TOTAL_LINE = re.compile(r"^TOTAL ([0-9]+) ([0-9]+)$")

SAMPLE = (
    "assignee,status\n"
    "alice,open\n"
    "alice,open\n"
    "alice,closed\n"
    "alice,open\n"
    "alice,closed\n"
    "bob,open\n"
    "carol,closed\n"
    "carol,closed\n"
    "carol,closed\n"
)
SAMPLE_REPORT = [
    "alice 3 2",
    "bob 1 0",
    "carol 0 3",
    "TOTAL 4 5",
]

RESULTS = []
SANDBOX = tempfile.mkdtemp(prefix="ticket-tests-")


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


def write_text(text, name="input.csv"):
    path = os.path.join(SANDBOX, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def run_tool(*args):
    return subprocess.run(
        ["bash", SCRIPT, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def run_csv(text, name="input.csv"):
    return run_tool(write_text(text, name))


def stdout_lines(proc):
    return proc.stdout.splitlines()


def per_assignee(proc):
    """Return ``{assignee: (open, closed)}`` parsed from stdout."""
    rows = {}
    for line in stdout_lines(proc):
        if line.startswith("TOTAL "):
            continue
        match = ASSIGNEE_LINE.match(line)
        if match:
            rows[match.group(1)] = (int(match.group(2)), int(match.group(3)))
    return rows


def total(proc):
    matches = [TOTAL_LINE.match(line) for line in stdout_lines(proc)]
    matches = [match for match in matches if match]
    assert len(matches) == 1, "expected exactly one TOTAL line, got %r" % (
        proc.stdout,
    )
    return int(matches[0].group(1)), int(matches[0].group(2))


# --- REQ-001: the entry point ------------------------------------------------


def req001_entry_point_exists_at_repo_root():
    assert os.path.isfile(SCRIPT), "missing entry point: %s" % SCRIPT


def req001_valid_csv_exits_zero_and_writes_only_the_report():
    proc = run_csv(SAMPLE)
    assert proc.returncode == 0, "exit %d, stderr=%r" % (proc.returncode, proc.stderr)
    assert stdout_lines(proc) == SAMPLE_REPORT, repr(proc.stdout)


def req001_missing_file_exits_non_zero_with_stderr_diagnostic():
    proc = run_tool(os.path.join(SANDBOX, "no-such-file.csv"))
    assert proc.returncode != 0, "expected a non-zero exit, got 0"
    assert proc.stdout == "", "stdout must stay empty, got %r" % proc.stdout
    assert proc.stderr.strip(), "expected a diagnostic on stderr"


def req001_a_directory_instead_of_a_file_is_an_error():
    proc = run_tool(SANDBOX)
    assert proc.returncode != 0, "expected a non-zero exit, got 0"
    assert proc.stdout == "", "stdout must stay empty, got %r" % proc.stdout
    assert proc.stderr.strip(), "expected a diagnostic on stderr"


def req001_no_argument_is_a_usage_error():
    proc = run_tool()
    assert proc.returncode != 0, "expected a non-zero exit, got 0"
    assert proc.stdout == "", "stdout must stay empty, got %r" % proc.stdout
    assert "usage" in proc.stderr.lower(), repr(proc.stderr)


def req001_empty_file_is_a_usage_error():
    proc = run_csv("", "empty.csv")
    assert proc.returncode != 0, "expected a non-zero exit, got 0"
    assert proc.stdout == "", "stdout must stay empty, got %r" % proc.stdout
    assert proc.stderr.strip(), "expected a diagnostic on stderr"


# --- REQ-002: header resolution ---------------------------------------------


def req002_reversed_header_order_produces_the_same_report():
    forward = run_csv(SAMPLE, "forward.csv")
    reversed_csv = (
        "status,assignee\n"
        "open,alice\n"
        "open,alice\n"
        "closed,alice\n"
        "open,alice\n"
        "closed,alice\n"
        "open,bob\n"
        "closed,carol\n"
        "closed,carol\n"
        "closed,carol\n"
    )
    backward = run_csv(reversed_csv, "reversed.csv")
    assert forward.returncode == 0 and backward.returncode == 0, "both runs must succeed"
    assert forward.stdout == backward.stdout, "reversed header changed the report"
    assert stdout_lines(backward) == SAMPLE_REPORT, repr(backward.stdout)


def req002_header_without_status_exits_non_zero_and_prints_nothing():
    proc = run_csv("assignee,team\nalice,core\n", "no-status.csv")
    assert proc.returncode != 0, "expected a non-zero exit, got 0"
    assert proc.stdout == "", "stdout must stay empty, got %r" % proc.stdout
    assert "status" in proc.stderr.lower(), repr(proc.stderr)


def req002_header_without_assignee_exits_non_zero_and_prints_nothing():
    proc = run_csv("status,team\nopen,core\n", "no-assignee.csv")
    assert proc.returncode != 0, "expected a non-zero exit, got 0"
    assert proc.stdout == "", "stdout must stay empty, got %r" % proc.stdout
    assert "assignee" in proc.stderr.lower(), repr(proc.stderr)


def req002_header_only_file_prints_total_zero():
    proc = run_csv("assignee,status\n", "header-only.csv")
    assert proc.returncode == 0, "exit %d, stderr=%r" % (proc.returncode, proc.stderr)
    assert proc.stdout == "TOTAL 0 0\n", repr(proc.stdout)


def req002_extra_ignored_columns_and_mixed_case_header_names_are_allowed():
    csv_text = (
        "ID,Assignee,Team,STATUS\n"
        "1,alice,core,open\n"
        "2,alice,core,closed\n"
    )
    proc = run_csv(csv_text, "extra-columns.csv")
    assert proc.returncode == 0, "exit %d, stderr=%r" % (proc.returncode, proc.stderr)
    assert stdout_lines(proc) == ["alice 1 1", "TOTAL 1 1"], repr(proc.stdout)


# --- REQ-003: per-assignee lines --------------------------------------------


def req003_alice_prints_one_line_with_three_open_and_two_closed():
    proc = run_csv(SAMPLE)
    lines = [line for line in stdout_lines(proc) if line.startswith("alice ")]
    assert lines == ["alice 3 2"], repr(lines)


def req003_assignee_with_no_rows_in_one_status_still_prints_both_numbers():
    proc = run_csv(SAMPLE)
    assert "bob 1 0" in stdout_lines(proc), repr(proc.stdout)
    assert "carol 0 3" in stdout_lines(proc), repr(proc.stdout)


def req003_lines_are_in_ascending_byte_order():
    csv_text = (
        "assignee,status\n"
        "bob,open\n"
        "alice,open\n"
        "Zoe,open\n"
        "émile,open\n"
    )
    proc = run_csv(csv_text, "order.csv")
    expected = ["Zoe 1 0", "alice 1 0", "bob 1 0", "émile 1 0", "TOTAL 4 0"]
    assert stdout_lines(proc) == expected, repr(proc.stdout)


def req003_assignee_is_printed_trimmed():
    csv_text = "assignee,status\n  alice  ,open\n"
    proc = run_csv(csv_text, "trimmed.csv")
    assert stdout_lines(proc) == ["alice 1 0", "TOTAL 1 0"], repr(proc.stdout)


# --- REQ-004: the totals line ------------------------------------------------


def req004_two_assignees_end_with_total_3_4():
    csv_text = (
        "assignee,status\n"
        "dana,open\n"
        "dana,open\n"
        "dana,closed\n"
        "erin,open\n"
        "erin,closed\n"
        "erin,closed\n"
        "erin,closed\n"
    )
    proc = run_csv(csv_text, "totals.csv")
    assert stdout_lines(proc) == ["dana 2 1", "erin 1 3", "TOTAL 3 4"], repr(proc.stdout)


def req004_total_equals_the_sums_of_the_printed_lines():
    proc = run_csv(SAMPLE)
    rows = per_assignee(proc)
    open_sum = sum(value[0] for value in rows.values())
    closed_sum = sum(value[1] for value in rows.values())
    assert total(proc) == (open_sum, closed_sum), repr(proc.stdout)


def req004_stdout_contains_only_assignee_lines_and_one_total():
    proc = run_csv(SAMPLE)
    lines = stdout_lines(proc)
    assert lines[-1].startswith("TOTAL "), repr(lines)
    assert sum(1 for line in lines if line.startswith("TOTAL ")) == 1, repr(lines)
    for line in lines[:-1]:
        assert ASSIGNEE_LINE.match(line), "unexpected stdout line: %r" % line


def req004_empty_report_is_exactly_total_zero():
    proc = run_csv("assignee,status\n", "only-header.csv")
    assert proc.stdout == "TOTAL 0 0\n", repr(proc.stdout)


# --- REQ-005 / AMB-001: recognised status values ----------------------------


def req005_pending_rows_are_counted_in_neither_column():
    csv_text = (
        "assignee,status\n"
        "alice,open\n"
        "alice,pending\n"
        "alice,closed\n"
    )
    proc = run_csv(csv_text, "pending.csv")
    assert stdout_lines(proc) == ["alice 1 1", "TOTAL 1 1"], repr(proc.stdout)


def req005_open_and_closed_are_recognised_with_whitespace_and_case():
    csv_text = (
        "assignee,status\n"
        "alice, Open \n"
        "alice,CLOSED\n"
        "alice, oPeN \n"
    )
    proc = run_csv(csv_text, "case.csv")
    assert stdout_lines(proc) == ["alice 2 1", "TOTAL 2 1"], repr(proc.stdout)


def amb001_unrecognised_status_makes_the_row_unusable():
    # AMB-001 (strict): `in-progress` is not open, closed, or counted at all.
    csv_text = (
        "assignee,status\n"
        "alice,open\n"
        "alice,in-progress\n"
        "bob,in-progress\n"
    )
    proc = run_csv(csv_text, "in-progress.csv")
    assert stdout_lines(proc) == ["alice 1 0", "TOTAL 1 0"], repr(proc.stdout)
    assert "skipped 2 rows" in proc.stderr, repr(proc.stderr)


# --- REQ-006 / AMB-002: unusable rows ---------------------------------------


def req006_malformed_row_leaves_the_stdout_report_unchanged():
    with_bad = (
        "assignee,status\n"
        "alice,open\n"
        "bob,closed,extra\n"
        "carol,closed\n"
        "dave,open\n"
        "erin,closed\n"
    )
    without_bad = (
        "assignee,status\n"
        "alice,open\n"
        "carol,closed\n"
        "dave,open\n"
        "erin,closed\n"
    )
    bad = run_csv(with_bad, "with-bad.csv")
    good = run_csv(without_bad, "without-bad.csv")
    assert bad.returncode == 0, "exit %d" % bad.returncode
    assert bad.stdout == good.stdout, "the malformed row changed stdout"


def req006_skipped_diagnostic_is_on_stderr_and_never_on_stdout():
    csv_text = (
        "assignee,status\n"
        "alice,open\n"
        "bob,closed,extra\n"
        ",open\n"
        "carol,\n"
        "dave,pending\n"
    )
    proc = run_csv(csv_text, "skips.csv")
    assert proc.returncode == 0, "skipping must still exit 0, got %d" % proc.returncode
    assert "skipped" not in proc.stdout.lower(), repr(proc.stdout)
    assert "skipped 4 rows" in proc.stderr, repr(proc.stderr)
    assert stdout_lines(proc) == ["alice 1 0", "TOTAL 1 0"], repr(proc.stdout)


def req006_skipped_count_is_stated_for_a_clean_file_too():
    proc = run_csv("assignee,status\nalice,open\n", "clean.csv")
    assert "skipped 0 rows" in proc.stderr, repr(proc.stderr)


def req006_short_row_and_whitespace_only_assignee_are_skipped():
    csv_text = (
        "assignee,status\n"
        "alice,open\n"
        "bob\n"
        "   ,closed\n"
    )
    proc = run_csv(csv_text, "short.csv")
    assert stdout_lines(proc) == ["alice 1 0", "TOTAL 1 0"], repr(proc.stdout)
    assert "skipped 2 rows" in proc.stderr, repr(proc.stderr)


# --- AMB-003 / AMB-004 / AMB-005: grouping, duplicates, quoting -------------


def amb003_assignee_names_are_compared_case_sensitively():
    csv_text = (
        "assignee,status\n"
        "alice,open\n"
        "Alice,open\n"
        "alice,closed\n"
    )
    proc = run_csv(csv_text, "casing.csv")
    assert stdout_lines(proc) == ["Alice 1 0", "alice 1 1", "TOTAL 2 1"], repr(
        proc.stdout,
    )


def amb004_identical_rows_count_as_two_tickets():
    csv_text = (
        "assignee,status\n"
        "alice,open\n"
        "alice,open\n"
    )
    proc = run_csv(csv_text, "duplicates.csv")
    assert stdout_lines(proc) == ["alice 2 0", "TOTAL 2 0"], repr(proc.stdout)


def amb005_quoted_fields_keep_commas_and_doubled_quotes():
    csv_text = (
        "assignee,status\n"
        '"Doe, John",open\n'
        '"O""Brien",closed\n'
        '"Doe, John",closed\n'
    )
    proc = run_csv(csv_text, "quoted.csv")
    assert stdout_lines(proc) == [
        "Doe, John 1 1",
        'O"Brien 0 1',
        "TOTAL 1 2",
    ], repr(proc.stdout)


def amb005_quoted_status_field_is_read_as_one_field():
    csv_text = 'assignee,status\n"alice","open"\n"bob","closed"\n'
    proc = run_csv(csv_text, "quoted-status.csv")
    assert stdout_lines(proc) == ["alice 1 0", "bob 0 1", "TOTAL 1 1"], repr(
        proc.stdout,
    )


TESTS = [
    ("req001_entry_point_exists_at_repo_root", req001_entry_point_exists_at_repo_root),
    (
        "req001_valid_csv_exits_zero_and_writes_only_the_report",
        req001_valid_csv_exits_zero_and_writes_only_the_report,
    ),
    (
        "req001_missing_file_exits_non_zero_with_stderr_diagnostic",
        req001_missing_file_exits_non_zero_with_stderr_diagnostic,
    ),
    (
        "req001_a_directory_instead_of_a_file_is_an_error",
        req001_a_directory_instead_of_a_file_is_an_error,
    ),
    ("req001_no_argument_is_a_usage_error", req001_no_argument_is_a_usage_error),
    ("req001_empty_file_is_a_usage_error", req001_empty_file_is_a_usage_error),
    (
        "req002_reversed_header_order_produces_the_same_report",
        req002_reversed_header_order_produces_the_same_report,
    ),
    (
        "req002_header_without_status_exits_non_zero_and_prints_nothing",
        req002_header_without_status_exits_non_zero_and_prints_nothing,
    ),
    (
        "req002_header_without_assignee_exits_non_zero_and_prints_nothing",
        req002_header_without_assignee_exits_non_zero_and_prints_nothing,
    ),
    ("req002_header_only_file_prints_total_zero", req002_header_only_file_prints_total_zero),
    (
        "req002_extra_ignored_columns_and_mixed_case_header_names_are_allowed",
        req002_extra_ignored_columns_and_mixed_case_header_names_are_allowed,
    ),
    (
        "req003_alice_prints_one_line_with_three_open_and_two_closed",
        req003_alice_prints_one_line_with_three_open_and_two_closed,
    ),
    (
        "req003_assignee_with_no_rows_in_one_status_still_prints_both_numbers",
        req003_assignee_with_no_rows_in_one_status_still_prints_both_numbers,
    ),
    ("req003_lines_are_in_ascending_byte_order", req003_lines_are_in_ascending_byte_order),
    ("req003_assignee_is_printed_trimmed", req003_assignee_is_printed_trimmed),
    ("req004_two_assignees_end_with_total_3_4", req004_two_assignees_end_with_total_3_4),
    (
        "req004_total_equals_the_sums_of_the_printed_lines",
        req004_total_equals_the_sums_of_the_printed_lines,
    ),
    (
        "req004_stdout_contains_only_assignee_lines_and_one_total",
        req004_stdout_contains_only_assignee_lines_and_one_total,
    ),
    ("req004_empty_report_is_exactly_total_zero", req004_empty_report_is_exactly_total_zero),
    (
        "req005_pending_rows_are_counted_in_neither_column",
        req005_pending_rows_are_counted_in_neither_column,
    ),
    (
        "req005_open_and_closed_are_recognised_with_whitespace_and_case",
        req005_open_and_closed_are_recognised_with_whitespace_and_case,
    ),
    ("amb001_unrecognised_status_makes_the_row_unusable", amb001_unrecognised_status_makes_the_row_unusable),
    (
        "req006_malformed_row_leaves_the_stdout_report_unchanged",
        req006_malformed_row_leaves_the_stdout_report_unchanged,
    ),
    (
        "req006_skipped_diagnostic_is_on_stderr_and_never_on_stdout",
        req006_skipped_diagnostic_is_on_stderr_and_never_on_stdout,
    ),
    (
        "req006_skipped_count_is_stated_for_a_clean_file_too",
        req006_skipped_count_is_stated_for_a_clean_file_too,
    ),
    (
        "req006_short_row_and_whitespace_only_assignee_are_skipped",
        req006_short_row_and_whitespace_only_assignee_are_skipped,
    ),
    (
        "amb003_assignee_names_are_compared_case_sensitively",
        amb003_assignee_names_are_compared_case_sensitively,
    ),
    (
        "amb004_identical_rows_count_as_two_tickets",
        amb004_identical_rows_count_as_two_tickets,
    ),
    (
        "amb005_quoted_fields_keep_commas_and_doubled_quotes",
        amb005_quoted_fields_keep_commas_and_doubled_quotes,
    ),
    (
        "amb005_quoted_status_field_is_read_as_one_field",
        amb005_quoted_status_field_is_read_as_one_field,
    ),
]


def write_report():
    directory = os.path.dirname(os.path.abspath(TAP_OUT))
    if directory:
        os.makedirs(directory, exist_ok=True)
    lines = ["1..%d" % len(RESULTS)]
    for index, (passed, name, diagnostic) in enumerate(RESULTS, 1):
        lines.append("%s %d - %s" % ("ok" if passed else "not ok", index, name))
        if not passed:
            for detail in str(diagnostic).splitlines() or [""]:
                lines.append("# %s" % detail)
    report = "\n".join(lines) + "\n"
    with open(TAP_OUT, "w", encoding="utf-8") as handle:
        handle.write(report)
    sys.stdout.write(report)


def main():
    for name, function in TESTS:
        check(name, function)
    write_report()
    return 0 if all(passed for passed, _, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
