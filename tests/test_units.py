#!/usr/bin/env python3
"""Unit tests for the functions behind ``bash summary.sh``.

These checks import ``summary.py`` directly and exercise one function at a time.
They are deliberately separate from ``tests/test_summary.py`` (which drives the
real entry point in a subprocess): together the two files form the delivered
suite, and ``bash run-tests.sh`` runs both through the same TAP harness.

Every function returns normally on success and raises ``AssertionError`` on
failure. ``UNIT_TESTS`` lists ``(name, function)`` pairs for the TAP runner.
"""

import csv
import io
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import summary  # noqa: E402 - importing the delivery under test

COLUMNS = {"suite": 0, "passed": 1, "total": 2}


# --- REQ-002: header detection and column lookup ------------------------------


def unit_locate_columns_reads_the_header_by_name():
    assert summary.locate_columns(["suite", "passed", "total"]) == (
        {"suite": 0, "passed": 1, "total": 2},
        True,
    )


def unit_locate_columns_follows_a_reordered_header():
    assert summary.locate_columns(["total", "suite", "passed"]) == (
        {"suite": 1, "passed": 2, "total": 0},
        True,
    )


def unit_locate_columns_ignores_header_blanks_and_case():
    assert summary.locate_columns([" Suite ", "PASSED", "Total"]) == (
        {"suite": 0, "passed": 1, "total": 2},
        True,
    )


def unit_locate_columns_requires_every_declared_name():
    assert summary.locate_columns(["suite", "passed"]) == (
        dict(summary.DEFAULT_COLUMNS),
        False,
    )


def unit_locate_columns_treats_a_data_row_as_data():
    assert summary.locate_columns(["alpha", "1", "2"]) == (
        dict(summary.DEFAULT_COLUMNS),
        False,
    )


# --- AMB-001 / REQ-004: exact, half-up percentage rendering -------------------


def unit_render_tenths_rounds_an_exact_half_away_from_zero():
    # 62.5 tenths is 6.25 percentage points: AMB-001 says 6.3, not 6.2.
    assert summary.render_tenths(Fraction(625, 10)) == "6.3"
    assert summary.render_tenths(Fraction(1, 2)) == "0.1"
    assert summary.render_tenths(Fraction(-1, 2)) == "-0.1"


def unit_render_tenths_truncates_below_a_half():
    assert summary.render_tenths(Fraction(624, 10)) == "6.2"
    assert summary.render_tenths(Fraction(1, 3)) == "0.0"
    assert summary.render_tenths(Fraction(4)) == "0.4"


def unit_render_tenths_always_prints_one_decimal():
    assert summary.render_tenths(Fraction(0)) == "0.0"
    assert summary.render_tenths(Fraction(999)) == "99.9"
    assert summary.render_tenths(Fraction(1000)) == "100.0"


def unit_percentage_uses_points_and_half_up():
    assert summary.percentage(Fraction(48), Fraction(50)) == "96.0"
    assert summary.percentage(Fraction(12), Fraction(12)) == "100.0"
    assert summary.percentage(Fraction(1), Fraction(3)) == "33.3"
    assert summary.percentage(Fraction(1), Fraction(16)) == "6.3"
    assert summary.percentage(Fraction(1), Fraction(2000)) == "0.1"
    assert summary.percentage(Fraction(1999), Fraction(2000)) == "100.0"
    assert summary.percentage(Fraction(2), Fraction(3)) == "66.7"
    assert summary.percentage(Fraction(0), Fraction(5)) == "0.0"


# --- REQ-004 / REQ-005: exact count rendering --------------------------------


def unit_render_count_keeps_exact_integers_and_decimals():
    assert summary.render_count(Fraction(0)) == "0"
    assert summary.render_count(Fraction(5)) == "5"
    assert summary.render_count(Fraction(11, 2)) == "5.5"
    assert summary.render_count(Fraction(123, 10)) == "12.3"
    assert summary.render_count(Fraction(1, 8)) == "0.125"
    assert summary.render_count(Fraction(-3, 2)) == "-1.5"


def unit_render_count_bounds_a_repeating_fraction():
    # Counts come from CSV cells, so a repeating denominator can only arise from
    # a decimal cell: keep the rendering finite instead of looping forever.
    assert summary.render_count(Fraction(1, 3)) == "0." + "3" * 24


# --- AMB-003: one row is usable or silently skipped --------------------------


def unit_parse_row_accepts_integer_decimal_and_signed_counts():
    assert summary.parse_row(["a", "1", "2"], COLUMNS) == (
        "a",
        Fraction(1),
        Fraction(2),
    )
    assert summary.parse_row(["a", "1.5", "3"], COLUMNS) == (
        "a",
        Fraction(3, 2),
        Fraction(3),
    )
    assert summary.parse_row(["a", "+1", "+2"], COLUMNS) == (
        "a",
        Fraction(1),
        Fraction(2),
    )


def unit_parse_row_reads_the_located_columns():
    columns = {"suite": 1, "passed": 2, "total": 0}
    assert summary.parse_row(["2", "a", "1"], columns) == (
        "a",
        Fraction(1),
        Fraction(2),
    )


def unit_parse_row_skips_every_unusable_row():
    for row in (
        ["a", "abc", "2"],  # non-numeric passed
        ["a", "1", "abc"],  # non-numeric total
        ["a", "1", "0"],  # zero total
        ["a", "1", "0.0"],  # zero total written as a decimal
        ["a", "-1", "2"],  # negative passed
        ["a", "1", "-2"],  # negative total
        ["a", "1"],  # short row
        [],  # empty row
        ["", "1", "2"],  # blank suite id
    ):
        assert summary.parse_row(row, COLUMNS) is None, row


def unit_parse_row_does_not_trim_the_suite_id():
    parsed = summary.parse_row([" a ", "1", "2"], COLUMNS)
    assert parsed[0] == " a "


# --- AMB-002 / REQ-003 / REQ-005: aggregation --------------------------------


def unit_summarise_merges_a_repeated_suite():
    records = [["suite", "passed", "total"], ["a", "1", "2"], ["a", "1", "2"]]
    assert summary.summarise(records) == ["a 2 4 50.0", "TOTAL 4"]


def unit_summarise_keeps_first_appearance_order():
    records = [
        ["suite", "passed", "total"],
        ["z", "1", "2"],
        ["a", "1", "2"],
        ["z", "1", "2"],
    ]
    assert summary.summarise(records) == [
        "z 2 4 50.0",
        "a 1 2 50.0",
        "TOTAL 6",
    ]


def unit_summarise_skips_unusable_rows_without_a_counter():
    records = [
        ["suite", "passed", "total"],
        ["ok", "1", "2"],
        ["bad", "x", "2"],
        ["bad", "1", "0"],
    ]
    assert summary.summarise(records) == ["ok 1 2 50.0", "TOTAL 2"]


def unit_summarise_totals_decimal_denominators():
    records = [
        ["suite", "passed", "total"],
        ["a", "1", "2.5"],
        ["b", "1", "4.5"],
    ]
    assert summary.summarise(records) == [
        "a 1 2.5 40.0",
        "b 1 4.5 22.2",
        "TOTAL 7",
    ]


def unit_summarise_ignores_a_parser_error_record():
    assert summary.summarise([None, ["a", "1", "2"]]) == [
        "a 1 2 50.0",
        "TOTAL 2",
    ]


def unit_summarise_reports_zero_total_for_empty_input():
    assert summary.summarise([]) == ["TOTAL 0"]


# --- AMB-003: parser-level failures become skipped rows ----------------------


def unit_read_records_yields_every_csv_record():
    handle = io.StringIO("a,1,2\n\nb,3,4\n")
    assert list(summary.read_records(handle)) == [
        ["a", "1", "2"],
        [],
        ["b", "3", "4"],
    ]


def unit_read_records_turns_a_csv_error_into_a_skipped_record():
    class BrokenReader:
        def __init__(self):
            self.step = 0

        def __iter__(self):
            return self

        def __next__(self):
            self.step += 1
            if self.step == 1:
                return ["a", "1", "2"]
            if self.step == 2:
                raise csv.Error("malformed record")
            raise StopIteration

    original = summary.csv.reader
    try:
        summary.csv.reader = lambda handle: BrokenReader()
        assert list(summary.read_records(io.StringIO(""))) == [
            ["a", "1", "2"],
            None,
        ]
    finally:
        summary.csv.reader = original


# --- REQ-001: the module-level entry point -----------------------------------


def unit_main_rejects_a_wrong_argument_count():
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = summary.main(["summary.py"])
    assert status == 2, status
    assert out.getvalue() == "", out.getvalue()
    assert "usage" in err.getvalue().lower(), err.getvalue()


def unit_main_stops_on_unreadable_input():
    out, err = io.StringIO(), io.StringIO()
    missing = os.path.join(tempfile.gettempdir(), "summary-no-such-input.csv")
    with redirect_stdout(out), redirect_stderr(err):
        status = summary.main(["summary.py", missing])
    assert status == 1, status
    assert out.getvalue() == "", out.getvalue()
    assert "cannot read" in err.getvalue(), err.getvalue()


def unit_main_writes_the_report_to_stdout():
    with tempfile.TemporaryDirectory(prefix="summary-unit-") as directory:
        path = os.path.join(directory, "input.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("suite,passed,total\na,1,2\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = summary.main(["summary.py", path])
    assert status == 0, status
    assert out.getvalue() == "a 1 2 50.0\nTOTAL 2\n", out.getvalue()
    assert err.getvalue() == "", err.getvalue()


UNIT_TESTS = [
    ("unit_locate_columns_reads_the_header_by_name", unit_locate_columns_reads_the_header_by_name),
    ("unit_locate_columns_follows_a_reordered_header", unit_locate_columns_follows_a_reordered_header),
    ("unit_locate_columns_ignores_header_blanks_and_case", unit_locate_columns_ignores_header_blanks_and_case),
    ("unit_locate_columns_requires_every_declared_name", unit_locate_columns_requires_every_declared_name),
    ("unit_locate_columns_treats_a_data_row_as_data", unit_locate_columns_treats_a_data_row_as_data),
    ("unit_render_tenths_rounds_an_exact_half_away_from_zero", unit_render_tenths_rounds_an_exact_half_away_from_zero),
    ("unit_render_tenths_truncates_below_a_half", unit_render_tenths_truncates_below_a_half),
    ("unit_render_tenths_always_prints_one_decimal", unit_render_tenths_always_prints_one_decimal),
    ("unit_percentage_uses_points_and_half_up", unit_percentage_uses_points_and_half_up),
    ("unit_render_count_keeps_exact_integers_and_decimals", unit_render_count_keeps_exact_integers_and_decimals),
    ("unit_render_count_bounds_a_repeating_fraction", unit_render_count_bounds_a_repeating_fraction),
    ("unit_parse_row_accepts_integer_decimal_and_signed_counts", unit_parse_row_accepts_integer_decimal_and_signed_counts),
    ("unit_parse_row_reads_the_located_columns", unit_parse_row_reads_the_located_columns),
    ("unit_parse_row_skips_every_unusable_row", unit_parse_row_skips_every_unusable_row),
    ("unit_parse_row_does_not_trim_the_suite_id", unit_parse_row_does_not_trim_the_suite_id),
    ("unit_summarise_merges_a_repeated_suite", unit_summarise_merges_a_repeated_suite),
    ("unit_summarise_keeps_first_appearance_order", unit_summarise_keeps_first_appearance_order),
    ("unit_summarise_skips_unusable_rows_without_a_counter", unit_summarise_skips_unusable_rows_without_a_counter),
    ("unit_summarise_totals_decimal_denominators", unit_summarise_totals_decimal_denominators),
    ("unit_summarise_ignores_a_parser_error_record", unit_summarise_ignores_a_parser_error_record),
    ("unit_summarise_reports_zero_total_for_empty_input", unit_summarise_reports_zero_total_for_empty_input),
    ("unit_read_records_yields_every_csv_record", unit_read_records_yields_every_csv_record),
    ("unit_read_records_turns_a_csv_error_into_a_skipped_record", unit_read_records_turns_a_csv_error_into_a_skipped_record),
    ("unit_main_rejects_a_wrong_argument_count", unit_main_rejects_a_wrong_argument_count),
    ("unit_main_stops_on_unreadable_input", unit_main_stops_on_unreadable_input),
    ("unit_main_writes_the_report_to_stdout", unit_main_writes_the_report_to_stdout),
]
