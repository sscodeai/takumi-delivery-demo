#!/usr/bin/env python3
"""Unit tests for the functions behind ``bash passrate.sh``.

These checks import ``passrate.py`` directly and exercise one function at a
time. They are separate from ``tests/test_passrate.py`` (which drives the real
entry point in subprocesses): together the two files form the delivered suite,
and ``bash run-tests.sh`` runs both through the same TAP harness.

Every function returns normally on success and raises ``AssertionError`` on
failure. ``UNIT_TESTS`` lists ``(name, function)`` pairs for the TAP runner.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import passrate  # noqa: E402 - importing the delivery under test


# --- REQ-003: header resolution ----------------------------------------------


def unit_looks_like_header_accepts_the_declared_header():
    assert passrate.looks_like_header(["suite", "passed", "total"]) is True


def unit_looks_like_header_accepts_any_order_and_extra_columns():
    for record in (
        ["total", "suite", "passed"],
        ["id", "suite", "total", "passed"],
        [" Suite ", " PASSED ", " TOTAL "],
    ):
        assert passrate.looks_like_header(record) is True, record


def unit_looks_like_header_rejects_a_headerless_sample_row():
    assert passrate.looks_like_header(["auth", "48", "50"]) is False


def unit_looks_like_header_treats_an_unusable_first_row_as_a_header():
    for record in (
        ["auth", "forty", "50"],
        ["auth", "48"],
        ["auth", "48", "50", "extra"],
        passrate.MALFORMED,
    ):
        assert passrate.looks_like_header(record) is True, record


def unit_resolve_columns_reports_every_position():
    assert passrate.resolve_columns(["total", "suite", "passed"]) == {
        "suite": 1,
        "passed": 2,
        "total": 0,
    }


def unit_resolve_columns_ignores_case_and_blanks():
    assert passrate.resolve_columns([" SUITE ", "Passed", " TOTAL "]) == {
        "suite": 0,
        "passed": 1,
        "total": 2,
    }


def unit_resolve_columns_ignores_extra_columns():
    assert passrate.resolve_columns(["note", "suite", "passed", "total"]) == {
        "suite": 1,
        "passed": 2,
        "total": 3,
    }


def unit_resolve_columns_names_each_missing_column():
    for header, missing in (
        (["passed", "total"], "suite"),
        (["suite", "total"], "passed"),
        (["suite", "passed"], "total"),
        (["note", "other"], "suite"),
    ):
        try:
            passrate.resolve_columns(header)
        except passrate.InputError as exc:
            text = str(exc)
            assert missing in text, "%r not named in %r" % (missing, text)
            continue
        raise AssertionError("%r must be rejected as a header" % (header,))


# --- REQ-006: counting --------------------------------------------------------


def unit_parse_count_accepts_non_negative_integers():
    assert passrate.parse_count("0") == 0
    assert passrate.parse_count("48") == 48
    assert passrate.parse_count(" 50 ") == 50
    assert passrate.parse_count("+7") == 7


def unit_parse_count_rejects_everything_else():
    for text in ("", " ", "-1", "48.0", "1e3", "abc", "1,000", "+", "$5"):
        assert passrate.parse_count(text) is None, text


def unit_parse_row_reads_the_resolved_columns():
    columns = passrate.resolve_columns(["total", "suite", "passed"])
    assert passrate.parse_row(["50", " auth ", "48"], columns, 3) == ("auth", 48, 50)


def unit_parse_row_rejects_unusable_rows():
    columns = passrate.resolve_columns(["suite", "passed", "total"])
    for record in (
        ["auth", "48"],  # wrong field count
        ["auth", "48", "50", "extra"],  # wrong field count
        ["auth", "x", "50"],  # non-integer passed
        ["auth", "48", "x"],  # non-integer total
        ["auth", "-1", "50"],  # negative passed
        ["auth", "48", "-50"],  # negative total
        ["auth", "48", "0"],  # total is zero
        ["auth", "48.0", "50"],  # not an integer
        passrate.MALFORMED,
    ):
        assert passrate.parse_row(record, columns, 3) is None, record


def unit_parse_row_keeps_passed_above_total():
    # The requirement lists the malformed cases exhaustively; a percentage
    # above 100 is still computable, so the row is counted.
    columns = passrate.resolve_columns(["suite", "passed", "total"])
    assert passrate.parse_row(["auth", "5", "4"], columns, 3) == ("auth", 5, 4)


# --- AMB-001: one-decimal half-up percentage ---------------------------------


def unit_format_percentage_prints_one_decimal():
    assert passrate.format_percentage(48, 50) == "96.0"
    assert passrate.format_percentage(17, 20) == "85.0"
    assert passrate.format_percentage(5, 5) == "100.0"
    assert passrate.format_percentage(0, 3) == "0.0"


def unit_format_percentage_rounds_exact_half_away_from_zero():
    # 1/16 = 6.25% -> 6.3 (truncate would print 6.2)
    assert passrate.format_percentage(1, 16) == "6.3"
    # 3/16 = 18.75% -> 18.8
    assert passrate.format_percentage(3, 16) == "18.8"
    # 1921/2000 = 96.05% -> 96.1
    assert passrate.format_percentage(1921, 2000) == "96.1"


def unit_format_percentage_rounds_a_value_just_below_a_half_down():
    # 2401/2500 = 96.04% -> 96.0
    assert passrate.format_percentage(2401, 2500) == "96.0"
    # 1/7 = 14.2857...% -> 14.3
    assert passrate.format_percentage(1, 7) == "14.3"


def unit_format_percentage_rounds_a_half_below_one_percent_up():
    # 1/2000 = 0.05% -> 0.1 (the truncate option would print 0.0)
    assert passrate.format_percentage(1, 2000) == "0.1"


# --- summarise: the report built from records --------------------------------


def unit_summarise_merges_a_repeated_suite():
    lines = passrate.summarise(
        [
            ["suite", "passed", "total"],
            ["auth", "48", "50"],
            ["auth", "1", "1"],
        ]
    )
    assert lines == ["auth 49 51 96.1", "TOTAL 49 51"], lines


def unit_summarise_reads_a_headerless_sample():
    lines = passrate.summarise(
        [
            ["auth", "48", "50"],
            ["billing", "17", "20"],
        ]
    )
    assert lines == ["auth 48 50 96.0", "billing 17 20 85.0", "TOTAL 65 70"], lines


def unit_summarise_reports_skipped_only_when_something_was_skipped():
    clean = passrate.summarise([["suite", "passed", "total"], ["auth", "1", "2"]])
    assert clean[-1] == "TOTAL 1 2", clean
    dirty = passrate.summarise(
        [["suite", "passed", "total"], ["auth", "1", "2"], ["auth", "x", "2"]]
    )
    assert dirty == ["auth 1 2 50.0", "TOTAL 1 2", "SKIPPED 1"], dirty


def unit_summarise_rejects_an_empty_file():
    try:
        passrate.summarise([])
    except passrate.InputError:
        return
    raise AssertionError("an empty file must be a fatal input error")


def unit_summarise_counts_each_malformed_shape_once():
    for row in (
        ["auth", "1"],  # wrong field count
        ["auth", "1", "2", "extra"],  # wrong field count
        ["auth", "x", "2"],  # non-integer passed
        ["auth", "1", "x"],  # non-integer total
        ["auth", "-1", "2"],  # negative passed
        ["auth", "1", "-2"],  # negative total
        ["auth", "0", "0"],  # total is zero
    ):
        lines = passrate.summarise([["suite", "passed", "total"], row])
        assert lines == ["TOTAL 0 0", "SKIPPED 1"], (row, lines)


UNIT_TESTS = [
    (name, value)
    for name, value in sorted(globals().items())
    if name.startswith("unit_") and callable(value)
]
