#!/usr/bin/env python3
"""Unit tests for the helpers behind ``bash summary.sh``.

These checks import ``summary.py`` directly and exercise one function at a
time, separate from ``tests/test_summary.py`` (which drives the real entry
point in subprocesses).  Together the two files are the delivered suite.

Every function returns normally on success and raises ``AssertionError`` on
failure.  The TAP report is written to ``reports/tests-units.tap`` (override
with ``TAP_OUT``) by the shared runner.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (str(TESTS_DIR), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import summary  # noqa: E402
from _tap import run_tests  # noqa: E402


def test_parse_count_accepts_non_negative_integers() -> None:
    assert summary.parse_count("0") == 0
    assert summary.parse_count("7") == 7
    assert summary.parse_count(" 12 ") == 12
    assert summary.parse_count("+5") == 5
    assert summary.parse_count("007") == 7


def test_parse_count_rejects_non_integers_and_signs() -> None:
    for text in ("", " ", "-1", "1.5", "abc", "1e3", "+", "1,2"):
        assert summary.parse_count(text) is None, text


def test_format_percentage_uses_one_decimal() -> None:
    cases = {
        (45, 50): "90.0",
        (2, 3): "66.7",
        (7, 15): "46.7",
        (19, 20): "95.0",
        (1, 8): "12.5",
        (1, 3): "33.3",
        (0, 5): "0.0",
        (5, 5): "100.0",
    }
    for (passed, total), expected in cases.items():
        assert summary.format_percentage(passed, total) == expected


def test_format_percentage_rounds_an_exact_half_up() -> None:
    # 1/16 = 6.25% and 1/32 = 3.125%; one decimal rounds them to 6.3 and 3.1.
    assert summary.format_percentage(1, 16) == "6.3"
    assert summary.format_percentage(1, 32) == "3.1"


def test_format_percentage_zero_total_is_zero_point_zero() -> None:
    assert summary.format_percentage(0, 0) == "0.0"


def test_header_order_recognises_the_declared_header() -> None:
    assert summary.header_order(["suite", "passed", "total"]) == (0, 1, 2)
    assert summary.header_order(["total", "passed", "suite"]) == (2, 1, 0)
    assert summary.header_order([" Suite ", " PASSED ", " Total "]) == (0, 1, 2)
    assert summary.header_order(["\ufeffsuite", "passed", "total"]) == (0, 1, 2)


def test_header_order_rejects_data_and_wrong_headers() -> None:
    assert summary.header_order(["login", "45", "50"]) is None
    assert summary.header_order(["suite", "passed"]) is None
    assert summary.header_order(["suite", "passed", "total", "extra"]) is None
    assert summary.header_order(["suite", "suite", "total"]) is None


def test_read_records_skips_blank_lines_and_keeps_line_numbers() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.csv"
        path.write_text("suite,passed,total\n\nlogin,45,50\n", encoding="utf-8")
        records = summary.read_records(str(path))
    assert records == [
        (1, ["suite", "passed", "total"]),
        (3, ["login", "45", "50"]),
    ]


def test_read_records_reports_an_unreadable_path() -> None:
    try:
        summary.read_records(str(ROOT / "does-not-exist.csv"))
    except summary.InputError as exc:
        assert "cannot read" in str(exc)
    else:
        raise AssertionError("missing file did not raise InputError")


def test_parse_row_accepts_a_valid_record_and_trims_the_suite() -> None:
    assert summary.parse_row([" login ", " 45 ", " 50 "], (0, 1, 2), 4) == (
        "login",
        45,
        50,
    )
    assert summary.parse_row(["50", "45", "login"], (2, 1, 0), 4) == (
        "login",
        45,
        50,
    )


def test_parse_row_rejects_every_malformed_shape_naming_the_line() -> None:
    columns = (0, 1, 2)
    malformed = (
        ["a", "1"],
        ["a", "1", "2", "extra"],
        ["a", "1.5", "2"],
        ["a", "1", "2.5"],
        ["a", "-1", "2"],
        ["a", "1", "-2"],
        ["a", "3", "2"],
        ["a", "x", "2"],
        ["a", "1", "y"],
    )
    for row in malformed:
        try:
            summary.parse_row(row, columns, 9)
        except summary.InputError as exc:
            assert "line 9" in str(exc), (row, str(exc))
        else:
            raise AssertionError("malformed row was accepted: %r" % (row,))


def test_build_report_prints_first_appearance_order_and_totals() -> None:
    records = [
        (1, ["suite", "passed", "total"]),
        (2, ["login", "45", "50"]),
        (3, ["search", "19", "20"]),
        (4, ["billing", "7", "8"]),
    ]
    assert summary.build_report(records) == (
        "login 45 50 90.0\n"
        "search 19 20 95.0\n"
        "billing 7 8 87.5\n"
        "TOTAL 71 78\n"
    )


def test_build_report_merges_repeated_suites() -> None:
    records = [
        (1, ["suite", "passed", "total"]),
        (2, ["api", "2", "3"]),
        (3, ["web", "5", "10"]),
        (4, ["api", "1", "3"]),
    ]
    assert summary.build_report(records) == (
        "api 3 6 50.0\n"
        "web 5 10 50.0\n"
        "TOTAL 8 16\n"
    )


def test_build_report_prints_zero_rate_for_a_zero_total() -> None:
    records = [
        (1, ["suite", "passed", "total"]),
        (2, ["empty", "0", "0"]),
    ]
    assert summary.build_report(records) == "empty 0 0 0.0\nTOTAL 0 0\n"


def test_build_report_with_only_a_header_is_an_empty_report() -> None:
    assert summary.build_report([(1, ["suite", "passed", "total"])]) == "TOTAL 0 0\n"
    assert summary.build_report([]) == "TOTAL 0 0\n"


def test_build_report_accepts_a_headerless_first_record() -> None:
    records = [(1, ["login", "45", "50"])]
    assert summary.build_report(records) == "login 45 50 90.0\nTOTAL 45 50\n"


TESTS = (
    test_parse_count_accepts_non_negative_integers,
    test_parse_count_rejects_non_integers_and_signs,
    test_format_percentage_uses_one_decimal,
    test_format_percentage_rounds_an_exact_half_up,
    test_format_percentage_zero_total_is_zero_point_zero,
    test_header_order_recognises_the_declared_header,
    test_header_order_rejects_data_and_wrong_headers,
    test_read_records_skips_blank_lines_and_keeps_line_numbers,
    test_read_records_reports_an_unreadable_path,
    test_parse_row_accepts_a_valid_record_and_trims_the_suite,
    test_parse_row_rejects_every_malformed_shape_naming_the_line,
    test_build_report_prints_first_appearance_order_and_totals,
    test_build_report_merges_repeated_suites,
    test_build_report_prints_zero_rate_for_a_zero_total,
    test_build_report_with_only_a_header_is_an_empty_report,
    test_build_report_accepts_a_headerless_first_record,
)


if __name__ == "__main__":
    raise SystemExit(run_tests(TESTS, "reports/tests-units.tap"))
