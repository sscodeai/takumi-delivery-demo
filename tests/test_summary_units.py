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
from decimal import Decimal
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for candidate in (str(TESTS_DIR), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import summary  # noqa: E402  (path is set up above)
from _tap import run_tests  # noqa: E402


# --- REQ-002: header handling ----------------------------------------------


def test_looks_like_header_recognises_the_declared_names() -> None:
    assert summary.looks_like_header(["region", "amount"]) is True
    assert summary.looks_like_header(["amount", "region"]) is True
    assert summary.looks_like_header(["\ufeffRegion", " Amount "]) is True


def test_looks_like_header_rejects_a_data_row() -> None:
    assert summary.looks_like_header(["North", "120.50"]) is False


def test_resolve_columns_follows_names_not_positions() -> None:
    assert summary.resolve_columns(["region", "amount"]) == (0, 1)
    assert summary.resolve_columns(["amount", "region"]) == (1, 0)


def test_resolve_columns_ignores_extra_columns() -> None:
    assert summary.resolve_columns(["channel", "amount", "region"]) == (2, 1)


def test_resolve_columns_rejects_a_header_without_both_columns() -> None:
    for header in (["region", "channel"], ["amount", "channel"], ["x"]):
        try:
            summary.resolve_columns(header)
        except summary.InputError:
            pass
        else:
            raise AssertionError(f"header accepted without both columns: {header}")


def test_is_blank_record_treats_empty_and_whitespace_lines_as_blank() -> None:
    assert summary.is_blank_record([]) is True
    assert summary.is_blank_record(["", ""]) is True
    assert summary.is_blank_record(["   ", "\t"]) is True
    assert summary.is_blank_record(["North", ""]) is False


# --- AMB-001 / AMB-004: amount parsing -------------------------------------


def test_parse_amount_accepts_numeric_forms() -> None:
    assert summary.parse_amount("120.50") == Decimal("120.50")
    assert summary.parse_amount(" 7 ") == Decimal("7")
    assert summary.parse_amount("0") == Decimal("0")
    assert summary.parse_amount("1e3") == Decimal("1000")


def test_parse_amount_accepts_negative_refunds() -> None:
    # AMB-004 (include): a negative amount is a well-formed record.
    assert summary.parse_amount("-25.00") == Decimal("-25.00")


def test_parse_amount_rejects_unusable_values() -> None:
    for text in ("", "   ", "abc", "1,200", "NaN", "Infinity", "-inf"):
        assert summary.parse_amount(text) is None, text


# --- REQ-003 / REQ-004 / REQ-005: aggregation -------------------------------


def test_summarise_records_counts_and_sums_per_region() -> None:
    counts, totals, skipped = summary.summarise_records(
        ["region", "amount"],
        [
            ["North", "120.50"],
            ["North", "99.50"],
            ["South", "80.25"],
        ],
    )
    assert counts == {"North": 2, "South": 1}
    assert totals == {"North": Decimal("220.00"), "South": Decimal("80.25")}
    assert skipped == 0


def test_summarise_records_skips_and_counts_malformed_rows() -> None:
    # AMB-001 (skip-count): unusable rows never reach the aggregates.
    counts, totals, skipped = summary.summarise_records(
        ["region", "amount"],
        [
            ["North", "abc"],
            ["", "5.00"],
            ["South"],
            ["West", "10.00"],
        ],
    )
    assert counts == {"West": 1}
    assert totals == {"West": Decimal("10.00")}
    assert skipped == 3


def test_summarise_records_merges_identical_rows() -> None:
    # AMB-002 (merge): each row is its own order, so nothing is de-duplicated.
    counts, totals, _ = summary.summarise_records(
        ["region", "amount"], [["North", "120.50"], ["North", "120.50"]]
    )
    assert counts == {"North": 2}
    assert totals == {"North": Decimal("241.00")}


def test_summarise_records_ignores_blank_rows() -> None:
    counts, totals, skipped = summary.summarise_records(
        ["region", "amount"],
        [[], ["", ""], ["North", "1.00"]],
    )
    assert counts == {"North": 1}
    assert totals == {"North": Decimal("1.00")}
    assert skipped == 0


def test_summarise_records_uses_named_columns() -> None:
    counts, totals, skipped = summary.summarise_records(
        ["amount", "channel", "region"],
        [["1.00", "web", "North"]],
    )
    assert counts == {"North": 1}
    assert totals == {"North": Decimal("1.00")}
    assert skipped == 0


# --- AMB-003 / REQ-006: formatting -----------------------------------------


def test_format_amount_prints_exactly_two_decimals() -> None:
    assert summary.format_amount(Decimal("110")) == "110.00"
    assert summary.format_amount(Decimal("45")) == "45.00"
    assert summary.format_amount(Decimal("0")) == "0.00"


def test_format_amount_rounds_half_up() -> None:
    assert summary.format_amount(Decimal("86.3125")) == "86.31"
    assert summary.format_amount(Decimal("10.005")) == "10.01"
    assert summary.format_amount(Decimal("2.675")) == "2.68"


def test_format_amount_rounds_negative_halves_away_from_zero() -> None:
    assert summary.format_amount(Decimal("-10.005")) == "-10.01"
    assert summary.format_amount(Decimal("-2.675")) == "-2.68"


def test_format_amount_never_prints_negative_zero() -> None:
    assert summary.format_amount(Decimal("-0.001")) == "0.00"


# --- REQ-003 / REQ-004 / REQ-005: the report --------------------------------


def test_format_report_renders_sorted_region_lines_then_total_then_skipped() -> None:
    counts = {"South": 1, "North": 2, "East": 1}
    totals = {
        "South": Decimal("80.25"),
        "North": Decimal("220.00"),
        "East": Decimal("45.00"),
    }
    assert summary.format_report(counts, totals, 0) == [
        "East 1 45.00 45.00",
        "North 2 220.00 110.00",
        "South 1 80.25 80.25",
        "TOTAL 4 345.25",
        "SKIPPED 0",
    ]


def test_format_report_is_empty_apart_from_total_and_skipped() -> None:
    assert summary.format_report({}, {}, 0) == ["TOTAL 0 0.00", "SKIPPED 0"]


def test_format_report_always_prints_the_skipped_count_last() -> None:
    lines = summary.format_report({"North": 1}, {"North": Decimal("1.00")}, 7)
    assert lines[-1] == "SKIPPED 7"


def test_format_report_has_no_overall_mean_on_the_total_line() -> None:
    lines = summary.format_report({"North": 2}, {"North": Decimal("3.00")}, 0)
    assert lines[-2] == "TOTAL 2 3.00"
    assert len(lines[-2].split(" ")) == 3


TESTS = [
    test_looks_like_header_recognises_the_declared_names,
    test_looks_like_header_rejects_a_data_row,
    test_resolve_columns_follows_names_not_positions,
    test_resolve_columns_ignores_extra_columns,
    test_resolve_columns_rejects_a_header_without_both_columns,
    test_is_blank_record_treats_empty_and_whitespace_lines_as_blank,
    test_parse_amount_accepts_numeric_forms,
    test_parse_amount_accepts_negative_refunds,
    test_parse_amount_rejects_unusable_values,
    test_summarise_records_counts_and_sums_per_region,
    test_summarise_records_skips_and_counts_malformed_rows,
    test_summarise_records_merges_identical_rows,
    test_summarise_records_ignores_blank_rows,
    test_summarise_records_uses_named_columns,
    test_format_amount_prints_exactly_two_decimals,
    test_format_amount_rounds_half_up,
    test_format_amount_rounds_negative_halves_away_from_zero,
    test_format_amount_never_prints_negative_zero,
    test_format_report_renders_sorted_region_lines_then_total_then_skipped,
    test_format_report_is_empty_apart_from_total_and_skipped,
    test_format_report_always_prints_the_skipped_count_last,
    test_format_report_has_no_overall_mean_on_the_total_line,
]


if __name__ == "__main__":
    sys.exit(run_tests(TESTS, "reports/tests-units.tap"))
