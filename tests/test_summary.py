#!/usr/bin/env python3
"""Acceptance tests for the delivered ``bash summary.sh``.

Every check drives the real entry point in a subprocess, so what is asserted
is the behaviour a caller (and the delivery's reviewer) sees: the exact bytes
on stdout, the diagnostic on stderr and the exit status.

Contract under test (docs/requirements/intake.yaml, deliverable block)::

    run:          bash summary.sh {csv}
    region line:  <region> <count> <sum> <mean>
    total line:   TOTAL <count> <sum>
    skipped line: SKIPPED <skipped-count>

The report is written to ``reports/tests.tap`` (override with ``TAP_OUT``)
and echoed to stdout; the process exits 0 only when every check passes.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tap import ROOT, run_tests  # noqa: E402  (path is set up above)

FIXTURES = ROOT / "tests" / "fixtures"

# The exact sample the requirement document declares, which has NO header row.
DECLARED_SAMPLE: Tuple[Tuple[str, str], ...] = (
    ("North", "120.50"),
    ("South", "80.25"),
    ("North", "99.50"),
    ("East", "45.00"),
)

SAMPLE_REPORT = (
    "East 1 45.00 45.00\n"
    "North 2 220.00 110.00\n"
    "South 1 80.25 80.25\n"
    "TOTAL 4 345.25\n"
    "SKIPPED 0\n"
)


def run_tool(*args: str) -> subprocess.CompletedProcess:
    """Run ``bash summary.sh <args>`` from the repository root."""
    return subprocess.run(
        ["bash", "summary.sh", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=False,
    )


def out_of(result: subprocess.CompletedProcess) -> str:
    return result.stdout.decode("utf-8")


def err_of(result: subprocess.CompletedProcess) -> str:
    return result.stderr.decode("utf-8")


def write_csv(directory: str, name: str, rows: Sequence[Sequence[str]]) -> Path:
    path = Path(directory) / name
    path.write_text(
        "".join(",".join(row) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def report_lines(text: str) -> List[str]:
    assert text.endswith("\n"), f"report does not end with a newline: {text!r}"
    return text.splitlines()


def region_lines(text: str) -> List[str]:
    return [
        line
        for line in report_lines(text)
        if not line.startswith("TOTAL ") and not line.startswith("SKIPPED ")
    ]


# --- REQ-003: the declared sample ------------------------------------------


def test_declared_sample_without_a_header_produces_the_required_report() -> None:
    # The requirement's own sample has no header row, so the tool must accept
    # a headered file and this headerless one with the same report.
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(tmp, "sample.csv", DECLARED_SAMPLE)
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == SAMPLE_REPORT, out_of(result)


def test_sample_with_a_header_produces_the_same_report() -> None:
    rows = [("region", "amount"), *DECLARED_SAMPLE]
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(tmp, "sample.csv", rows)
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == SAMPLE_REPORT, out_of(result)


def test_shipped_sample_file_is_the_declared_sample() -> None:
    result = run_tool("sample/sales.csv")
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == SAMPLE_REPORT, out_of(result)


def test_per_region_count_sum_and_mean_are_printed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(
            tmp,
            "mixed.csv",
            [
                ("region", "amount"),
                ("North", "120.50"),
                ("North", "99.50"),
                ("South", "80.25"),
            ],
        )
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert "North 2 220.00 110.00\n" in out_of(result), out_of(result)
    assert "South 1 80.25 80.25\n" in out_of(result), out_of(result)


def test_region_lines_are_sorted_lexicographically_and_unique() -> None:
    result = run_tool(str(FIXTURES / "sorting.csv"))
    assert result.returncode == 0, err_of(result)
    lines = region_lines(out_of(result))
    assert lines == [
        "Beta 1 3.00 3.00",
        "Zed 1 1.00 1.00",
        "alpha 1 2.00 2.00",
    ], lines
    names = [line.split(" ", 1)[0] for line in lines]
    assert names == sorted(names), names
    assert len(names) == len(set(names)), names


def test_region_line_count_equals_distinct_regions() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    assert len(region_lines(out_of(result))) == 3, out_of(result)


def test_region_line_has_exactly_four_fields_in_the_declared_shape() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    for line in region_lines(out_of(result)):
        fields = line.split(" ")
        assert len(fields) == 4, line
        region, count, total, mean = fields
        assert region != "", line
        assert count.isdigit(), line
        assert _is_two_decimal(total), line
        assert _is_two_decimal(mean), line


def _is_two_decimal(text: str) -> bool:
    whole, dot, fraction = text.partition(".")
    return (
        dot == "."
        and len(fraction) == 2
        and fraction.isdigit()
        and whole.lstrip("-").isdigit()
    )


# --- REQ-002: header handling ----------------------------------------------


def test_columns_are_located_by_header_name_not_position() -> None:
    result = run_tool(str(FIXTURES / "reordered.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == SAMPLE_REPORT, out_of(result)


def test_extra_columns_do_not_change_the_numbers() -> None:
    result = run_tool(str(FIXTURES / "extra_column.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == SAMPLE_REPORT, out_of(result)


def test_blank_lines_are_neither_records_nor_skipped_rows() -> None:
    result = run_tool(str(FIXTURES / "blank_lines.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == SAMPLE_REPORT, out_of(result)


def test_region_and_amount_are_trimmed_but_the_region_name_keeps_its_case() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(
            tmp,
            "spaces.csv",
            [("region", "amount"), ("  North  ", " 120.50 ")],
        )
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == (
        "North 1 120.50 120.50\nTOTAL 1 120.50\nSKIPPED 0\n"
    ), out_of(result)


# --- REQ-004: the TOTAL line ------------------------------------------------


def test_total_line_is_printed_exactly_once_after_the_region_lines() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    lines = report_lines(out_of(result))
    totals = [line for line in lines if line.startswith("TOTAL ")]
    assert totals == ["TOTAL 4 345.25"], totals
    assert lines.index(totals[0]) > len(region_lines(out_of(result))) - 1
    assert lines[-2] == totals[0], lines


def test_total_line_carries_only_count_and_sum() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    total = report_lines(out_of(result))[-2]
    assert total == "TOTAL 4 345.25", total
    assert len(total.split(" ")) == 3, total


def test_total_count_and_sum_are_additive_over_the_region_lines() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    lines = report_lines(out_of(result))
    regions = region_lines(out_of(result))
    total_count = sum(int(line.split(" ")[1]) for line in regions)
    total_sum = sum(int(line.split(" ")[2].replace(".", "")) for line in regions)
    assert lines[-2] == f"TOTAL {total_count} {total_sum // 100}.{total_sum % 100:02d}", lines


# --- REQ-005: the SKIPPED line ---------------------------------------------


def test_skipped_line_is_always_last_and_zero_for_a_clean_file() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    lines = report_lines(out_of(result))
    assert lines[-1] == "SKIPPED 0", lines
    assert sum(1 for line in lines if line.startswith("SKIPPED ")) == 1, lines


def test_malformed_rows_are_skipped_counted_and_excluded_from_totals() -> None:
    result = run_tool(str(FIXTURES / "malformed.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == (
        "North 1 120.50 120.50\n"
        "West 1 10.00 10.00\n"
        "TOTAL 2 130.50\n"
        "SKIPPED 3\n"
    ), out_of(result)


def test_two_malformed_rows_are_counted_as_two() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(
            tmp,
            "two_bad.csv",
            [
                ("region", "amount"),
                ("North", "not-a-number"),
                ("North", "10.00"),
                ("South", ""),
            ],
        )
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result).endswith("TOTAL 1 10.00\nSKIPPED 2\n"), out_of(result)


# --- AMB-001: malformed rows ------------------------------------------------


def test_short_row_is_skipped_and_counted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(
            tmp, "short.csv", [("region", "amount"), ("North",), ("South", "5.00")]
        )
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == "South 1 5.00 5.00\nTOTAL 1 5.00\nSKIPPED 1\n", out_of(result)


def test_empty_region_is_skipped_and_counted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(
            tmp,
            "empty_region.csv",
            [("region", "amount"), ("", "5.00"), ("South", "5.00")],
        )
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == "South 1 5.00 5.00\nTOTAL 1 5.00\nSKIPPED 1\n", out_of(result)


# --- AMB-002: repeated rows -------------------------------------------------


def test_identical_rows_are_merged_into_the_aggregates() -> None:
    result = run_tool(str(FIXTURES / "duplicates.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == (
        "North 2 241.00 120.50\n"
        "TOTAL 2 241.00\n"
        "SKIPPED 0\n"
    ), out_of(result)


# --- AMB-003: rounding ------------------------------------------------------


def test_mean_with_more_than_two_decimals_rounds_half_up() -> None:
    # 345.25 / 4 == 86.3125 -> 86.31; a truncating tool would agree here.
    result = run_tool(str(FIXTURES / "rounding.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == (
        "Central 4 345.25 86.31\nTOTAL 4 345.25\nSKIPPED 0\n"
    ), out_of(result)


def test_mean_at_an_exact_half_rounds_away_from_zero() -> None:
    # 20.01 / 2 == 10.005 -> half-up 10.01; truncation would print 10.00.
    result = run_tool(str(FIXTURES / "half_up.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == (
        "Tie 2 20.01 10.01\nTOTAL 2 20.01\nSKIPPED 0\n"
    ), out_of(result)


def test_whole_number_mean_is_printed_with_two_decimals() -> None:
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    assert "North 2 220.00 110.00" in out_of(result), out_of(result)


def test_zero_amount_is_formatted_as_two_decimals() -> None:
    result = run_tool(str(FIXTURES / "zero.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == "Zero 1 0.00 0.00\nTOTAL 1 0.00\nSKIPPED 0\n", out_of(result)


# --- AMB-004: negative amounts ---------------------------------------------


def test_negative_amount_is_included_as_a_refund() -> None:
    result = run_tool(str(FIXTURES / "negative.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == (
        "North 2 75.00 37.50\nTOTAL 2 75.00\nSKIPPED 0\n"
    ), out_of(result)


# --- REQ-008: row-order invariance -----------------------------------------


def test_shuffling_data_rows_does_not_change_stdout_bytes() -> None:
    rows = list(DECLARED_SAMPLE)
    with tempfile.TemporaryDirectory() as tmp:
        ordered = write_csv(tmp, "ordered.csv", [("region", "amount"), *rows])
        baseline = run_tool(str(ordered))
        assert baseline.returncode == 0, err_of(baseline)
        random.Random(20261108).shuffle(rows)
        shuffled = write_csv(tmp, "shuffled.csv", [("region", "amount"), *rows])
        shuffled_result = run_tool(str(shuffled))
    assert shuffled_result.returncode == 0, err_of(shuffled_result)
    assert shuffled_result.stdout == baseline.stdout, (
        baseline.stdout,
        shuffled_result.stdout,
    )


def test_repeated_runs_are_byte_identical() -> None:
    first = run_tool(str(FIXTURES / "mixed.csv"))
    second = run_tool(str(FIXTURES / "mixed.csv"))
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout


def test_input_file_is_not_modified() -> None:
    before = (FIXTURES / "mixed.csv").read_bytes()
    result = run_tool(str(FIXTURES / "mixed.csv"))
    assert result.returncode == 0, err_of(result)
    assert (FIXTURES / "mixed.csv").read_bytes() == before


# --- REQ-009: empty report --------------------------------------------------


def test_header_only_file_prints_only_total_and_skipped() -> None:
    result = run_tool(str(FIXTURES / "header_only.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == "TOTAL 0 0.00\nSKIPPED 0\n", out_of(result)


def test_header_only_file_with_blank_lines_is_an_empty_report() -> None:
    result = run_tool(str(FIXTURES / "header_only_blank.csv"))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == "TOTAL 0 0.00\nSKIPPED 0\n", out_of(result)


def test_empty_file_is_a_valid_empty_report() -> None:
    # REQ-001: a readable file exits 0 and prints the report; with no records
    # that report is the empty one.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "empty.csv"
        path.write_bytes(b"")
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == "TOTAL 0 0.00\nSKIPPED 0\n", out_of(result)


def test_blank_only_file_is_a_valid_empty_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "blank.csv"
        path.write_bytes(b"\n\n   \n")
        result = run_tool(str(path))
    assert result.returncode == 0, err_of(result)
    assert out_of(result) == "TOTAL 0 0.00\nSKIPPED 0\n", out_of(result)


# --- REQ-001: errors --------------------------------------------------------


def test_missing_argument_is_a_usage_error() -> None:
    result = run_tool()
    assert result.returncode != 0, result.returncode
    assert result.stdout == b"", result.stdout
    assert err_of(result).strip() != "", err_of(result)


def test_unreadable_path_is_an_error_with_no_partial_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        missing = str(Path(tmp) / "does-not-exist.csv")
        result = run_tool(missing)
    assert result.returncode != 0, result.returncode
    assert result.stdout == b"", result.stdout
    assert err_of(result).strip() != "", err_of(result)


def test_header_without_the_amount_column_stops_the_run() -> None:
    result = run_tool(str(FIXTURES / "bad_header.csv"))
    assert result.returncode != 0, result.returncode
    assert result.stdout == b"", result.stdout
    assert "amount" in err_of(result), err_of(result)


def test_header_without_the_region_column_stops_the_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_csv(
            tmp, "bad_header.csv", [("amount", "channel"), ("1.00", "web")]
        )
        result = run_tool(str(path))
    assert result.returncode != 0, result.returncode
    assert result.stdout == b"", result.stdout
    assert "region" in err_of(result), err_of(result)


TESTS = [
    test_declared_sample_without_a_header_produces_the_required_report,
    test_sample_with_a_header_produces_the_same_report,
    test_shipped_sample_file_is_the_declared_sample,
    test_per_region_count_sum_and_mean_are_printed,
    test_region_lines_are_sorted_lexicographically_and_unique,
    test_region_line_count_equals_distinct_regions,
    test_region_line_has_exactly_four_fields_in_the_declared_shape,
    test_columns_are_located_by_header_name_not_position,
    test_extra_columns_do_not_change_the_numbers,
    test_blank_lines_are_neither_records_nor_skipped_rows,
    test_region_and_amount_are_trimmed_but_the_region_name_keeps_its_case,
    test_total_line_is_printed_exactly_once_after_the_region_lines,
    test_total_line_carries_only_count_and_sum,
    test_total_count_and_sum_are_additive_over_the_region_lines,
    test_skipped_line_is_always_last_and_zero_for_a_clean_file,
    test_malformed_rows_are_skipped_counted_and_excluded_from_totals,
    test_two_malformed_rows_are_counted_as_two,
    test_short_row_is_skipped_and_counted,
    test_empty_region_is_skipped_and_counted,
    test_identical_rows_are_merged_into_the_aggregates,
    test_mean_with_more_than_two_decimals_rounds_half_up,
    test_mean_at_an_exact_half_rounds_away_from_zero,
    test_whole_number_mean_is_printed_with_two_decimals,
    test_zero_amount_is_formatted_as_two_decimals,
    test_negative_amount_is_included_as_a_refund,
    test_shuffling_data_rows_does_not_change_stdout_bytes,
    test_repeated_runs_are_byte_identical,
    test_input_file_is_not_modified,
    test_header_only_file_prints_only_total_and_skipped,
    test_header_only_file_with_blank_lines_is_an_empty_report,
    test_empty_file_is_a_valid_empty_report,
    test_blank_only_file_is_a_valid_empty_report,
    test_missing_argument_is_a_usage_error,
    test_unreadable_path_is_an_error_with_no_partial_report,
    test_header_without_the_amount_column_stops_the_run,
    test_header_without_the_region_column_stops_the_run,
]


if __name__ == "__main__":
    sys.exit(run_tests(TESTS, "reports/tests.tap"))
