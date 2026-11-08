#!/usr/bin/env python3
"""Acceptance tests for the per-assignee ticket summary.

Every check drives the real ``bash summary.sh <csv>`` command in a subprocess,
so the suite exercises exactly the entry point the requirement declares.  The
TAP report is written to ``reports/tests.tap`` (or ``$TAP_OUT``) and the runner
exits nonzero when any check fails.

Coverage required by docs/requirements/intake.yaml:
  REQ-001  entry point, sample file, argument handling
  REQ-002  header names, reordered/extra columns, RFC 4180 quoting
  REQ-003  per-assignee open/closed counts, single-status assignees
  REQ-004  byte-order sorting, row-order independence, locale independence
  REQ-005  empty report for a file with no counted rows
  AMB-001  trimmed, case-insensitive `open`/`closed`; other statuses skipped
  AMB-002  one line per assignee carrying both counts, no extra line
  AMB-003  bad rows skipped and counted on stderr; bad header is an error
  AMB-004  assignee trimmed but case preserved
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tap import ROOT, run_tests  # noqa: E402  (path is set up above)

SUMMARY = ROOT / "summary.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

MIXED = "alice 3 1\nbob 0 3\ncarol 1 0\n"
ZERO = "dave 2 0\nerin 0 1\n"
SKIPPED = "frank 2 1\n"
SORTED = "Alice 1 0\nZoe 1 0\nalice 1 1\nbob 0 1\nzoe 1 0\n"
SAMPLE = "alice 2 1\nbob 1 1\ncarol 1 0\n"


def run_tool(
    *args: str,
    cwd: Path = ROOT,
    extra_env: Dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    if extra_env:
        environment.update(extra_env)
    return subprocess.run(
        ["bash", str(SUMMARY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        # REQ-001: the tool must never wait for interactive input or hang.
        stdin=subprocess.DEVNULL,
        timeout=30,
    )


def report_for(name: str) -> str:
    result = run_tool(str(FIXTURES / name))
    assert result.returncode == 0, (
        f"bash summary.sh {name} exited {result.returncode}: {result.stderr}"
    )
    return result.stdout


def write_temp_csv(text: str, *, newline: str = "") -> str:
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".csv", delete=False, newline=newline, encoding="utf-8"
    )
    with handle:
        handle.write(text)
    return handle.name


def lines_of(report: str) -> List[str]:
    return report.splitlines()


def skipped_count(stderr: str) -> int:
    match = re.search(r"skipped (\d+) malformed", stderr)
    assert match is not None, f"no skipped-row count on stderr: {stderr!r}"
    return int(match.group(1))


def totals_of(report: str) -> tuple[int, int]:
    opened = closed = 0
    for line in lines_of(report):
        _, open_text, closed_text = line.rsplit(" ", 2)
        opened += int(open_text)
        closed += int(closed_text)
    return opened, closed


# --- REQ-001: entry point --------------------------------------------------


def test_entry_point_and_delivered_files_exist() -> None:
    assert SUMMARY.is_file(), "summary.sh is missing from the repository root"
    assert (ROOT / "run-tests.sh").is_file(), "run-tests.sh is missing"
    assert (ROOT / "mutation" / "run.sh").is_file(), "mutation/run.sh is missing"
    assert (ROOT / "sample" / "tickets.csv").is_file(), "sample/tickets.csv is missing"


def test_documented_invocation_on_the_sample_file() -> None:
    result = run_tool("sample/tickets.csv", cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout == SAMPLE
    assert result.stderr == ""


def test_runs_without_interactive_input_or_network() -> None:
    # REQ-001: stdin is already /dev/null in run_tool; point every proxy at a
    # closed port and confirm the report still comes out.
    result = run_tool(
        "sample/tickets.csv",
        extra_env={
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == SAMPLE
    assert result.stderr == ""


def test_relative_path_works_from_the_repository_root() -> None:
    result = subprocess.run(
        ["bash", "summary.sh", "tests/fixtures/mixed.csv"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == MIXED


def test_missing_argument_is_a_usage_error() -> None:
    result = subprocess.run(
        ["bash", str(SUMMARY)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0, "a missing CSV argument must be an error"
    assert result.stdout == "", "a usage error must not print a report"


def test_nonexistent_input_is_an_error_with_empty_stdout() -> None:
    result = run_tool(str(FIXTURES / "does-not-exist.csv"))
    assert result.returncode != 0, "a missing input file must be an error"
    assert result.stdout == "", "a failed run must not print a report"
    assert result.stderr.strip(), "a failed run must explain itself on stderr"


def test_input_file_is_not_modified() -> None:
    path = FIXTURES / "mixed.csv"
    before = path.read_bytes()
    report_for("mixed.csv")
    assert path.read_bytes() == before, "summary.sh modified its input file"


# --- REQ-002: header names and RFC 4180 ------------------------------------


def test_mixed_per_assignee_open_and_closed_counts() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == MIXED
    assert result.stderr == "", "a clean file must not report skipped rows"


def test_columns_are_located_by_header_name_not_position() -> None:
    assert report_for("reordered.csv") == MIXED
    assert report_for("extra_column.csv") == MIXED


def test_quoted_fields_follow_rfc4180() -> None:
    path = write_temp_csv(
        'assignee,status\r\n'
        '"Smith, Alice",open\r\n'
        '"Bob ""B"" Jones",closed\r\n'
        '"Carol\nNewline",open\r\n',
        newline="",
    )
    try:
        result = run_tool(path)
    finally:
        os.unlink(path)
    assert result.returncode == 0, result.stderr
    expected = (
        'Bob "B" Jones 0 1\n'
        "Carol\nNewline 1 0\n"
        "Smith, Alice 1 0\n"
    )
    assert result.stdout == expected


def test_quoted_assignee_with_a_comma_is_one_assignee() -> None:
    path = write_temp_csv(
        "assignee,status\n"
        '"Smith, Alice",open\n'
        '"Smith, Alice",closed\n'
        '"Smith, Alice",open\n'
    )
    try:
        result = run_tool(path)
    finally:
        os.unlink(path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'Smith, Alice 2 1\n'


def test_header_line_is_not_counted_as_a_ticket() -> None:
    names = [line.rsplit(" ", 2)[0] for line in lines_of(report_for("mixed.csv"))]
    assert "assignee" not in names
    assert "status" not in names


# --- REQ-003: counts -------------------------------------------------------


def test_every_counted_row_contributes_exactly_once() -> None:
    parsed = [
        (name, int(opened), int(closed))
        for name, opened, closed in (
            line.rsplit(" ", 2) for line in lines_of(report_for("mixed.csv"))
        )
    ]
    assert sum(opened for _, opened, _ in parsed) == 4
    assert sum(closed for _, _, closed in parsed) == 4
    data_rows = len((FIXTURES / "mixed.csv").read_text().splitlines()) - 1
    assert 4 + 4 == data_rows


def test_assignee_with_only_one_status_prints_a_zero() -> None:
    assert report_for("zero.csv") == ZERO


def test_three_open_one_closed_prints_the_required_line() -> None:
    # REQ-003's own acceptance example.
    assert "alice 3 1" in lines_of(report_for("mixed.csv"))


def test_no_assignee_outside_the_data_is_reported() -> None:
    names = {line.rsplit(" ", 2)[0] for line in lines_of(report_for("mixed.csv"))}
    assert names == {"alice", "bob", "carol"}


# --- REQ-004: deterministic order -----------------------------------------


def test_assignees_are_sorted_by_byte_order() -> None:
    # ASCII byte order is `A` < `Z` < `a` < `b` < `z`, so case matters.
    assert report_for("sorting.csv") == SORTED


def test_shuffling_data_rows_does_not_change_the_output() -> None:
    rows = (FIXTURES / "mixed.csv").read_text(encoding="utf-8").splitlines()
    header, data = rows[0], rows[1:]
    shuffled = list(data)
    random.Random(20261108).shuffle(shuffled)
    path = write_temp_csv("\n".join([header, *shuffled]) + "\n")
    try:
        result = run_tool(path)
    finally:
        os.unlink(path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == MIXED


def test_repeated_runs_are_byte_identical() -> None:
    first = run_tool(str(FIXTURES / "sorting.csv"))
    second = run_tool(str(FIXTURES / "sorting.csv"))
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout


def test_output_order_is_locale_independent() -> None:
    path = write_temp_csv("assignee,status\nzoe,open\nzo\u00eb,closed\n")
    try:
        result = run_tool(path, extra_env={"LC_ALL": "C", "LANG": "C"})
    finally:
        os.unlink(path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "zoe 1 0\nzo\u00eb 0 1\n"


# --- REQ-005: no counted rows ---------------------------------------------


def test_header_only_file_prints_nothing_and_exits_zero() -> None:
    result = run_tool(str(FIXTURES / "header_only.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_all_rows_skipped_prints_nothing_and_exits_zero() -> None:
    result = run_tool(str(FIXTURES / "all_skipped.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert skipped_count(result.stderr) == 4, result.stderr


# --- AMB-001: status recognition ------------------------------------------


def test_status_is_trimmed_and_case_insensitive() -> None:
    result = run_tool(str(FIXTURES / "status_variants.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ann 2 1\n"
    assert result.stderr == ""


def test_unrecognised_status_is_skipped_and_counted_on_stderr() -> None:
    result = run_tool(str(FIXTURES / "unknown_status.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ann 1 1\n"
    assert skipped_count(result.stderr) == 1, result.stderr


def test_assignee_seen_only_in_skipped_rows_gets_no_line() -> None:
    # REQ-005 + AMB-001/AMB-003: an assignee whose only rows were skipped must
    # not be invented with zero counts.
    result = run_tool(str(FIXTURES / "unknown_only.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ann 1 0\n"
    assert "zed" not in result.stdout
    assert skipped_count(result.stderr) == 2, result.stderr


# --- AMB-002: one line per assignee ---------------------------------------


def test_one_line_per_assignee_with_both_counts_and_nothing_else() -> None:
    lines = lines_of(report_for("mixed.csv"))
    assert len(lines) == 3, f"expected one line per assignee, saw {lines!r}"
    for line in lines:
        assert len(line.rsplit(" ", 2)) == 3, f"unexpected line shape: {line!r}"
    assert not any(line.startswith("TOTAL") for line in lines)
    assert len({line.rsplit(" ", 2)[0] for line in lines}) == len(lines)


# --- AMB-003: malformed rows and bad headers ------------------------------


def test_skipped_rows_are_counted_on_stderr_and_do_not_change_counts() -> None:
    result = run_tool(str(FIXTURES / "skipped.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == SKIPPED
    assert skipped_count(result.stderr) == 5, result.stderr
    assert totals_of(result.stdout) == (2, 1), "only the three good rows count"


def test_empty_assignee_rows_are_skipped_and_counted() -> None:
    result = run_tool(str(FIXTURES / "empty_assignee.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ann 1 0\n"
    assert skipped_count(result.stderr) == 2, result.stderr


def test_empty_status_rows_are_skipped_and_counted() -> None:
    result = run_tool(str(FIXTURES / "empty_status.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ann 1 0\n"
    assert skipped_count(result.stderr) == 2, result.stderr


def test_short_rows_are_skipped_and_counted() -> None:
    result = run_tool(str(FIXTURES / "short_row.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ann 1 0\n"
    assert skipped_count(result.stderr) == 1, result.stderr


def test_header_without_required_columns_stops_the_run() -> None:
    result = run_tool(str(FIXTURES / "bad_header.csv"))
    assert result.returncode != 0, "a header without the required columns must fail"
    assert result.stdout == ""
    assert "assignee" in result.stderr and "status" in result.stderr, result.stderr


def test_empty_file_stops_the_run() -> None:
    path = write_temp_csv("")
    try:
        result = run_tool(path)
    finally:
        os.unlink(path)
    assert result.returncode != 0, "an empty file has no usable header"
    assert result.stdout == ""
    assert result.stderr.strip()


# --- AMB-004: assignee normalisation --------------------------------------


def test_assignee_is_trimmed_but_case_is_preserved() -> None:
    result = run_tool(str(FIXTURES / "assignee_trim.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Alice 1 1\nalice 1 0\n"


TESTS = [
    test_entry_point_and_delivered_files_exist,
    test_documented_invocation_on_the_sample_file,
    test_runs_without_interactive_input_or_network,
    test_relative_path_works_from_the_repository_root,
    test_missing_argument_is_a_usage_error,
    test_nonexistent_input_is_an_error_with_empty_stdout,
    test_input_file_is_not_modified,
    test_mixed_per_assignee_open_and_closed_counts,
    test_columns_are_located_by_header_name_not_position,
    test_quoted_fields_follow_rfc4180,
    test_quoted_assignee_with_a_comma_is_one_assignee,
    test_header_line_is_not_counted_as_a_ticket,
    test_every_counted_row_contributes_exactly_once,
    test_assignee_with_only_one_status_prints_a_zero,
    test_three_open_one_closed_prints_the_required_line,
    test_no_assignee_outside_the_data_is_reported,
    test_assignees_are_sorted_by_byte_order,
    test_shuffling_data_rows_does_not_change_the_output,
    test_repeated_runs_are_byte_identical,
    test_output_order_is_locale_independent,
    test_header_only_file_prints_nothing_and_exits_zero,
    test_all_rows_skipped_prints_nothing_and_exits_zero,
    test_status_is_trimmed_and_case_insensitive,
    test_unrecognised_status_is_skipped_and_counted_on_stderr,
    test_assignee_seen_only_in_skipped_rows_gets_no_line,
    test_one_line_per_assignee_with_both_counts_and_nothing_else,
    test_skipped_rows_are_counted_on_stderr_and_do_not_change_counts,
    test_empty_assignee_rows_are_skipped_and_counted,
    test_empty_status_rows_are_skipped_and_counted,
    test_short_rows_are_skipped_and_counted,
    test_header_without_required_columns_stops_the_run,
    test_empty_file_stops_the_run,
    test_assignee_is_trimmed_but_case_is_preserved,
]


if __name__ == "__main__":
    sys.exit(run_tests(TESTS, "reports/tests.tap"))
