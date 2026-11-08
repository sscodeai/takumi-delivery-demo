#!/usr/bin/env python3
"""Acceptance tests for the delivered ``bash summary.sh``.

Every check drives the real entry point in a subprocess, so what is asserted
is the behaviour a caller sees: the exact bytes on stdout, the diagnostic on
stderr and the exit status.

Contract under test (docs/requirements/intake.yaml, deliverable block)::

    run:          bash summary.sh {csv}
    suite line:   <suite> <passed> <total> <percentage>
    total line:   TOTAL <passed_sum> <total_sum>

The report is written to ``reports/tests.tap`` (override with ``TAP_OUT``)
and echoed to stdout; the process exits 0 only when every check passes.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tap import ROOT, run_tests  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"

BASIC_REPORT = (
    "login 45 50 90.0\n"
    "search 19 20 95.0\n"
    "billing 7 8 87.5\n"
    "TOTAL 71 78\n"
)

PERCENTAGE = re.compile(r"^\d+\.\d$")


def run_tool(*args: str) -> subprocess.CompletedProcess:
    """Run ``bash summary.sh <args>`` from the repository root."""
    return subprocess.run(
        ["bash", "summary.sh", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def report_lines(text: str) -> List[str]:
    assert text.endswith("\n"), "report does not end with a newline: %r" % text
    return text.splitlines()


def suite_lines(text: str) -> List[str]:
    lines = report_lines(text)
    return lines[:-1]


def total_line(text: str) -> str:
    lines = report_lines(text)
    return lines[-1]


def parse_total(text: str) -> Tuple[int, int]:
    match = re.fullmatch(r"TOTAL (\d+) (\d+)", total_line(text))
    assert match is not None, "bad TOTAL line: %r" % total_line(text)
    return int(match.group(1)), int(match.group(2))


def test_declared_sample_with_header_produces_the_required_report() -> None:
    result = run_tool(str(ROOT / "sample" / "suites.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == BASIC_REPORT
    assert result.stderr == ""


def test_declared_headerless_sample_is_accepted() -> None:
    # The requirement's declared sample has no header line; the delivery
    # pipeline writes exactly those records, so the first data row must work.
    result = run_tool(str(FIXTURES / "headerless.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == BASIC_REPORT


def test_header_only_file_prints_only_total() -> None:
    result = run_tool(str(FIXTURES / "header_only.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "TOTAL 0 0\n"


def test_header_only_file_with_blank_lines_prints_only_total() -> None:
    result = run_tool(str(FIXTURES / "header_only_blank.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "TOTAL 0 0\n"


def test_empty_file_is_an_empty_report() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "empty.csv"
        path.write_text("", encoding="utf-8")
        result = run_tool(str(path))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "TOTAL 0 0\n"


def test_header_text_is_never_emitted_as_a_suite_line() -> None:
    result = run_tool(str(FIXTURES / "basic.csv"))
    assert result.returncode == 0, result.stderr
    assert "suite" not in result.stdout
    assert all(not line.startswith("suite ") for line in report_lines(result.stdout))


def test_three_valid_records_produce_three_suite_lines() -> None:
    result = run_tool(str(FIXTURES / "basic.csv"))
    assert result.returncode == 0, result.stderr
    assert len(suite_lines(result.stdout)) == 3


def test_two_thirds_rounds_half_up_to_66_7() -> None:
    result = run_tool(str(FIXTURES / "rounding.csv"))
    assert result.returncode == 0, result.stderr
    assert "two_thirds 2 3 66.7" in report_lines(result.stdout)
    assert "two_thirds 2 3 66.6" not in report_lines(result.stdout)


def test_an_exact_half_rounds_away_from_zero() -> None:
    result = run_tool(str(FIXTURES / "rounding.csv"))
    assert result.returncode == 0, result.stderr
    assert "exact_half 1 16 6.3" in report_lines(result.stdout)
    assert "below_half 1 32 3.1" in report_lines(result.stdout)
    assert "eighth 1 8 12.5" in report_lines(result.stdout)


def test_every_percentage_has_exactly_one_decimal_place() -> None:
    result = run_tool(str(FIXTURES / "rounding.csv"))
    assert result.returncode == 0, result.stderr
    for line in suite_lines(result.stdout):
        fields = line.split(" ")
        assert len(fields) == 4, line
        assert PERCENTAGE.match(fields[3]), line


def test_duplicate_suites_merge_in_first_appearance_order() -> None:
    result = run_tool(str(FIXTURES / "duplicates.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "api 7 15 46.7\n"
        "web 5 10 50.0\n"
        "TOTAL 12 25\n"
    )


def test_zero_total_suite_prints_zero_point_zero() -> None:
    result = run_tool(str(FIXTURES / "zero_total.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "empty 0 0 0.0\n"
        "ok 1 2 50.0\n"
        "TOTAL 1 2\n"
    )


def test_total_line_is_last_and_sum_of_printed_suite_lines() -> None:
    for name in ("basic.csv", "duplicates.csv", "rounding.csv", "zero_total.csv"):
        result = run_tool(str(FIXTURES / name))
        assert result.returncode == 0, result.stderr
        lines = report_lines(result.stdout)
        assert len(total_line(result.stdout).split(" ")) == 3
        passed_sum = 0
        total_sum = 0
        for line in lines[:-1]:
            fields = line.split(" ")
            assert len(fields) == 4, line
            passed_sum += int(fields[1])
            total_sum += int(fields[2])
        assert parse_total(result.stdout) == (passed_sum, total_sum), name


def test_no_line_contains_a_percent_sign() -> None:
    for name in ("basic.csv", "rounding.csv", "duplicates.csv"):
        result = run_tool(str(FIXTURES / name))
        assert result.returncode == 0, result.stderr
        assert "%" not in result.stdout


def test_blank_lines_are_ignored() -> None:
    result = run_tool(str(FIXTURES / "blank_lines.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "login 45 50 90.0\n"
        "search 19 20 95.0\n"
        "TOTAL 64 70\n"
    )


def test_surrounding_whitespace_on_fields_is_ignored() -> None:
    result = run_tool(str(FIXTURES / "whitespace.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "login 45 50 90.0\n"
        "search 19 20 95.0\n"
        "TOTAL 64 70\n"
    )


def test_a_reordered_header_is_resolved_by_name() -> None:
    result = run_tool(str(FIXTURES / "reordered.csv"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "login 45 50 90.0\n"
        "search 19 20 95.0\n"
        "TOTAL 64 70\n"
    )


def test_crlf_input_is_accepted() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "crlf.csv"
        path.write_bytes(
            b"suite,passed,total\r\nlogin,45,50\r\nsearch,19,20\r\nbilling,7,8\r\n"
        )
        result = run_tool(str(path))
    assert result.returncode == 0, result.stderr
    assert result.stdout == BASIC_REPORT


def test_missing_argument_is_a_usage_error() -> None:
    result = run_tool()
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() != ""


def test_nonexistent_file_is_an_error() -> None:
    result = run_tool(str(ROOT / "does-not-exist.csv"))
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() != ""


def test_directory_path_is_an_error() -> None:
    result = run_tool(str(ROOT))
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr.strip() != ""


def test_malformed_rows_stop_with_a_nonzero_exit_and_name_the_line() -> None:
    names = (
        "malformed_fields.csv",
        "malformed_noninteger.csv",
        "malformed_negative.csv",
        "malformed_passed_gt_total.csv",
    )
    for name in names:
        result = run_tool(str(FIXTURES / name))
        assert result.returncode != 0, name
        assert result.stdout == "", name
        assert "line 3" in result.stderr, (name, result.stderr)


def test_a_late_malformed_row_leaves_no_partial_report() -> None:
    result = run_tool(str(FIXTURES / "malformed_fields.csv"))
    assert result.returncode != 0
    assert result.stdout == ""


def test_input_file_is_not_modified() -> None:
    path = FIXTURES / "basic.csv"
    before = path.read_bytes()
    result = run_tool(str(path))
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == before


TESTS: Sequence = (
    test_declared_sample_with_header_produces_the_required_report,
    test_declared_headerless_sample_is_accepted,
    test_header_only_file_prints_only_total,
    test_header_only_file_with_blank_lines_prints_only_total,
    test_empty_file_is_an_empty_report,
    test_header_text_is_never_emitted_as_a_suite_line,
    test_three_valid_records_produce_three_suite_lines,
    test_two_thirds_rounds_half_up_to_66_7,
    test_an_exact_half_rounds_away_from_zero,
    test_every_percentage_has_exactly_one_decimal_place,
    test_duplicate_suites_merge_in_first_appearance_order,
    test_zero_total_suite_prints_zero_point_zero,
    test_total_line_is_last_and_sum_of_printed_suite_lines,
    test_no_line_contains_a_percent_sign,
    test_blank_lines_are_ignored,
    test_surrounding_whitespace_on_fields_is_ignored,
    test_a_reordered_header_is_resolved_by_name,
    test_crlf_input_is_accepted,
    test_missing_argument_is_a_usage_error,
    test_nonexistent_file_is_an_error,
    test_directory_path_is_an_error,
    test_malformed_rows_stop_with_a_nonzero_exit_and_name_the_line,
    test_a_late_malformed_row_leaves_no_partial_report,
    test_input_file_is_not_modified,
)


if __name__ == "__main__":
    raise SystemExit(run_tests(TESTS, "reports/tests.tap"))
