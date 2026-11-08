#!/usr/bin/env python3
"""Unit tests for the helpers behind ``bash summary.sh``.

The integration suite, ``tests/test_summary.py``, drives the real entry point in
a subprocess and is the acceptance evidence for ``docs/requirements/intake.yaml``.
This suite complements it by importing ``summary.py`` and checking the rules
that implement each acceptance criterion and each ``AMB-nnn`` decision at the
unit level, including edge values that are awkward to reach through the shell.

The report is written to ``reports/tests-summary-units.tap`` (override with
``TAP_OUT``) and echoed to stdout; the process exits 0 only when every check
passes.
"""

import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
from decimal import Decimal
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(ROOT, "summary.py")
TAP_OUT = os.environ.get(
    "TAP_OUT", os.path.join(ROOT, "reports", "tests-summary-units.tap")
)

NUMBER = re.compile(r"^-?[0-9]+\.[0-9]{2}$")
ASCII_TRIMS = " \t\r\n\f\v"

RESULTS = []


def load_summary():
    spec = importlib.util.spec_from_file_location("summary_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


summary = load_summary()


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


def raises(function, exception, contains=None):
    """Assert that ``function`` raises ``exception`` (optionally mentioning text)."""
    try:
        function()
    except exception as exc:
        if contains is not None:
            assert contains in str(exc), "%r not in %r" % (contains, str(exc))
        return exc
    raise AssertionError("expected %s, nothing was raised" % exception.__name__)


def records(*rows):
    return iter([["region", "amount"], *[list(row) for row in rows]])


# --------------------------------------------------------------------------
# parse_region -- REQ-008 / AMB-004 (exact-trimmed)
# --------------------------------------------------------------------------


def unit_parse_region_trims_every_ascii_whitespace_character():
    for pad in ASCII_TRIMS:
        assert summary.parse_region(pad + "north" + pad) == "north", repr(pad)


def unit_parse_region_keeps_internal_spacing():
    assert summary.parse_region(" north west ") == "north west"
    assert summary.parse_region("new  york") == "new  york"


def unit_parse_region_is_case_sensitive():
    assert summary.parse_region("north") == "north"
    assert summary.parse_region("North") == "North"
    assert summary.parse_region("NORTH") == "NORTH"
    assert summary.parse_region("north") != summary.parse_region("North")


def unit_parse_region_returns_none_for_blank_cells():
    assert summary.parse_region("") is None
    for pad in (" ", "\t", "\r\n", "\f\v"):
        assert summary.parse_region(pad) is None, repr(pad)


def unit_parse_region_does_not_trim_non_ascii_whitespace():
    # AMB-004 says *ASCII* whitespace; U+00A0 is part of the region key.
    assert summary.parse_region("\u00a0north\u00a0") == "\u00a0north\u00a0"


# --------------------------------------------------------------------------
# parse_amount -- REQ-005 / REQ-007 / REQ-009 / AMB-003
# --------------------------------------------------------------------------


def unit_parse_amount_accepts_plain_decimals_exactly():
    cases = {
        "0": Fraction(0),
        "0.00": Fraction(0),
        "-1": Fraction(-1),
        "+1.5": Fraction(3, 2),
        ".5": Fraction(1, 2),
        "3.": Fraction(3),
        "0001.20": Fraction(6, 5),
        "0.125": Fraction(1, 8),
        "-2.674": Fraction(-1337, 500),
        "100.00": Fraction(100),
    }
    for text, expected in cases.items():
        value = summary.parse_amount(text)
        assert value == expected, "%r -> %r, expected %r" % (text, value, expected)


def unit_parse_amount_rejects_unreadable_cells():
    bad = [
        "",
        " ",
        "abc",
        "1e3",
        "$5.00",
        "5%",
        "1.2.3",
        "--1",
        "1 000",
        "1,000",
        "NaN",
        "Infinity",
        "0x10",
        "1_000",
        " 5",
        "5 ",
        "+",
        "-",
        ".",
    ]
    for text in bad:
        assert summary.parse_amount(text) is None, repr(text)


def unit_parse_amount_keeps_negative_and_zero_as_valid_measures():
    assert summary.parse_amount("-40.00") == Fraction(-40)
    assert summary.parse_amount("0") == Fraction(0)
    assert summary.parse_amount("-0.00") == Fraction(0)


def unit_parse_amount_never_uses_binary_floats():
    total = summary.parse_amount("0.1") + summary.parse_amount("0.2")
    assert total == Fraction(3, 10)
    assert summary.parse_amount("0.3") == total


# --------------------------------------------------------------------------
# round_cents / format_cents / format_value -- REQ-007 / AMB-003 (half-up)
# --------------------------------------------------------------------------


def unit_round_cents_rounds_an_exact_half_away_from_zero():
    assert summary.round_cents(Fraction(1, 8)) == 13  # 0.125
    assert summary.round_cents(Fraction(-1, 8)) == -13
    assert summary.round_cents(Fraction(1, 200)) == 1  # 0.005
    assert summary.round_cents(Fraction(-1, 200)) == -1


def unit_round_cents_rounds_non_halves_by_nearest():
    assert summary.round_cents(Fraction("2.674")) == 267
    assert summary.round_cents(Fraction("-2.674")) == -267
    assert summary.round_cents(Fraction("0.124999")) == 12
    assert summary.round_cents(Fraction("0.125001")) == 13


def unit_round_cents_has_no_negative_zero():
    assert summary.round_cents(Fraction("-0.001")) == 0
    assert summary.format_cents(summary.round_cents(Fraction("-0.001"))) == "0.00"


def unit_round_cents_handles_large_and_fractional_values():
    assert summary.round_cents(Fraction(123456789, 1)) == 12345678900
    assert summary.round_cents(Fraction(1, 3)) == 33


def unit_format_cents_prints_exactly_two_decimals():
    cases = {
        0: "0.00",
        5: "0.05",
        123: "1.23",
        -123: "-1.23",
        100000: "1000.00",
        -1: "-0.01",
    }
    for cents, expected in cases.items():
        assert summary.format_cents(cents) == expected, (cents, expected)


def unit_format_value_composes_rounding_and_formatting():
    assert summary.format_value(Fraction(1, 8)) == "0.13"
    assert summary.format_value(Fraction(-1, 8)) == "-0.13"
    assert summary.format_value(Fraction("2.674")) == "2.67"
    assert summary.format_value(Fraction(100)) == "100.00"


def unit_format_value_always_matches_the_declared_shape():
    values = [
        Fraction(0),
        Fraction(1, 8),
        Fraction(-1, 8),
        Fraction("2.674"),
        Fraction(-40),
        Fraction(123456789, 1000),
    ]
    for value in values:
        text = summary.format_value(value)
        assert NUMBER.match(text), "%r -> %r" % (value, text)


# --------------------------------------------------------------------------
# header_columns -- REQ-002
# --------------------------------------------------------------------------


def unit_header_columns_resolves_the_declared_order():
    assert summary.header_columns(["region", "amount"]) == (2, 0, 1)


def unit_header_columns_resolves_swapped_columns():
    assert summary.header_columns(["amount", "region"]) == (2, 1, 0)


def unit_header_columns_ignores_extra_columns():
    assert summary.header_columns(["note", "amount", "id", "region"]) == (
        4,
        3,
        1,
    )


def unit_header_columns_trims_and_folds_names():
    assert summary.header_columns([" REGION ", "Amount"]) == (2, 0, 1)


def unit_header_columns_uses_the_first_matching_column():
    assert summary.header_columns(["region", "region", "amount"]) == (3, 0, 2)
    assert summary.header_columns(["amount", "region", "amount"]) == (3, 1, 0)


def unit_header_columns_missing_region_is_fatal():
    raises(
        lambda: summary.header_columns(["amount"]),
        summary.InputError,
        contains="region",
    )


def unit_header_columns_missing_amount_is_fatal():
    raises(
        lambda: summary.header_columns(["region"]),
        summary.InputError,
        contains="amount",
    )


def unit_header_columns_missing_both_names_both():
    exc = raises(
        lambda: summary.header_columns(["other"]),
        summary.InputError,
        contains="region",
    )
    assert "amount" in str(exc)


def unit_header_columns_rejects_an_unparsable_header():
    raises(
        lambda: summary.header_columns(summary.MALFORMED),
        summary.InputError,
        contains="header",
    )


# --------------------------------------------------------------------------
# read_records -- REQ-005 / AMB-001
# --------------------------------------------------------------------------


def unit_read_records_yields_plain_rows():
    stream = io.StringIO("region,amount\nnorth,1.00\nsouth,2.00\n")
    assert list(summary.read_records(stream)) == [
        ["region", "amount"],
        ["north", "1.00"],
        ["south", "2.00"],
    ]


def unit_read_records_handles_crlf_and_quoted_commas():
    stream = io.StringIO('region,amount\r\n"north, west",1.00\r\n')
    assert list(summary.read_records(stream)) == [
        ["region", "amount"],
        ["north, west", "1.00"],
    ]


def unit_read_records_turns_an_unparsable_record_into_the_malformed_sentinel():
    stream = io.StringIO('region,amount\n"unclosed,1.00\n')
    parsed = list(summary.read_records(stream))
    assert parsed[0] == ["region", "amount"]
    assert parsed[1] is summary.MALFORMED


# --------------------------------------------------------------------------
# summarise -- REQ-003 / REQ-004 / REQ-005 / REQ-006 / REQ-011
# --------------------------------------------------------------------------


def unit_summarise_declared_sample_is_exact():
    lines = summary.summarise(
        records(
            ("north", "100.00"),
            ("south", "50.00"),
            ("north", "25.50"),
            ("east", "10.25"),
        )
    )
    assert lines == [
        "east 10.25 10.25",
        "north 125.50 62.75",
        "south 50.00 50.00",
        "SKIPPED 0",
        "TOTAL 185.75 4",
    ]


def unit_summarise_header_only_is_an_empty_report():
    assert summary.summarise(iter([["region", "amount"]])) == [
        "SKIPPED 0",
        "TOTAL 0.00 0",
    ]


def unit_summarise_rejects_an_empty_file():
    raises(lambda: summary.summarise(iter([])), summary.InputError, contains="empty")


def unit_summarise_merges_every_duplicate_occurrence():
    lines = summary.summarise(
        records(("north", "10.00"), ("south", "4.00"), ("north", "10.00"))
    )
    assert lines == [
        "north 20.00 10.00",
        "south 4.00 4.00",
        "SKIPPED 0",
        "TOTAL 24.00 3",
    ]


def unit_summarise_three_valid_two_malformed():
    lines = summary.summarise(
        records(
            ("north", "10.00"),
            ("broken", "not-a-number"),
            ("south", "5.00"),
            ("", "7.00"),
            ("east", "2.00"),
        )
    )
    assert lines == [
        "east 2.00 2.00",
        "north 10.00 10.00",
        "south 5.00 5.00",
        "SKIPPED 2",
        "TOTAL 17.00 3",
    ]


def unit_summarise_all_malformed_counts_each_row_once():
    lines = summary.summarise(
        iter(
            [
                ["region", "amount"],
                ["north"],
                ["", "1.00"],
                ["north", "abc"],
                summary.MALFORMED,
            ]
        )
    )
    assert lines == ["SKIPPED 4", "TOTAL 0.00 0"]


def unit_summarise_wrong_field_count_is_malformed():
    lines = summary.summarise(
        records(("north",), ("south", "1.00", "extra"), ("east", "2.00"))
    )
    assert lines == ["east 2.00 2.00", "SKIPPED 2", "TOTAL 2.00 1"]


def unit_summarise_blank_region_is_malformed():
    lines = summary.summarise(
        records(("", "1.00"), (" \t ", "2.00"), ("east", "3.00"))
    )
    assert lines == ["east 3.00 3.00", "SKIPPED 2", "TOTAL 3.00 1"]


def unit_summarise_non_decimal_amount_is_malformed():
    lines = summary.summarise(records(("north", "1e3"), ("north", "2.00")))
    assert lines == ["north 2.00 2.00", "SKIPPED 1", "TOTAL 2.00 1"]


def unit_summarise_region_key_is_trimmed_and_case_sensitive():
    lines = summary.summarise(
        records((" north ", "1.00"), ("north", "2.00"), ("North", "4.00"))
    )
    assert lines == [
        "North 4.00 4.00",
        "north 3.00 1.50",
        "SKIPPED 0",
        "TOTAL 7.00 3",
    ]


def unit_summarise_sorts_region_lines_by_utf8_bytes():
    names = ["z", "A", "a", "B", "0", "_"]
    lines = summary.summarise(records(*[(name, "1.00") for name in names]))
    printed = [line.rsplit(" ", 2)[0] for line in lines[:-2]]
    assert printed == sorted(names, key=lambda name: name.encode("utf-8"))
    assert printed == ["0", "A", "B", "_", "a", "z"]


def unit_summarise_total_revenue_is_the_sum_of_printed_region_revenues():
    # Two sub-cent regions round up individually; the TOTAL adds the printed
    # cents, so REL-002 holds even when raw sums would round differently.
    lines = summary.summarise(
        records(("a", "0.005"), ("b", "0.005"), ("c", "1.10"))
    )
    assert lines == [
        "a 0.01 0.01",
        "b 0.01 0.01",
        "c 1.10 1.10",
        "SKIPPED 0",
        "TOTAL 1.12 3",
    ]


def unit_summarise_total_orders_is_the_sum_of_region_counts():
    lines = summary.summarise(
        records(
            ("a", "1.00"),
            ("a", "2.00"),
            ("a", "3.00"),
            ("b", "4.00"),
            ("b", "5.00"),
        )
    )
    assert lines == [
        "a 6.00 2.00",
        "b 9.00 4.50",
        "SKIPPED 0",
        "TOTAL 15.00 5",
    ]


def unit_summarise_average_uses_the_unrounded_sum():
    lines = summary.summarise(
        records(("north", "1.00"), ("north", "2.00"), ("north", "4.00"))
    )
    assert lines[0] == "north 7.00 2.33"


def unit_summarise_negative_values_stay_valid_and_format_with_a_sign():
    lines = summary.summarise(
        records(("north", "100.00"), ("north", "-40.00"), ("east", "-2.50"))
    )
    assert lines == [
        "east -2.50 -2.50",
        "north 60.00 30.00",
        "SKIPPED 0",
        "TOTAL 57.50 3",
    ]


def unit_summarise_zero_amounts_are_valid_orders():
    lines = summary.summarise(records(("north", "0.00")))
    assert lines == ["north 0.00 0.00", "SKIPPED 0", "TOTAL 0.00 1"]


def unit_summarise_never_prints_negative_zero():
    lines = summary.summarise(records(("north", "-0.001"), ("east", "-0.00")))
    assert lines == [
        "east 0.00 0.00",
        "north 0.00 0.00",
        "SKIPPED 0",
        "TOTAL 0.00 2",
    ]


def unit_summarise_prints_exactly_one_skipped_and_one_total_line():
    lines = summary.summarise(records(("north", "1.00"), ("bad", "x")))
    assert sum(1 for line in lines if line.startswith("SKIPPED ")) == 1
    assert sum(1 for line in lines if line.startswith("TOTAL ")) == 1
    assert lines[-2].startswith("SKIPPED ")
    assert lines[-1].startswith("TOTAL ")


# --------------------------------------------------------------------------
# main -- REQ-001 / REQ-012
# --------------------------------------------------------------------------


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = summary.main(argv)
    return status, out.getvalue(), err.getvalue()


def unit_main_requires_exactly_one_argument():
    for argv in ([], ["only-the-script"]):
        status, out, err = run_main(argv)
        assert status == 2, (argv, status)
        assert out == ""
        assert "usage" in err.lower()


def unit_main_missing_path_is_fatal_with_empty_stdout():
    with tempfile.TemporaryDirectory() as directory:
        missing = os.path.join(directory, "does-not-exist.csv")
        status, out, err = run_main(["summary.py", missing])
    assert status == 1
    assert out == ""
    assert err.strip() != ""


def unit_main_empty_file_is_fatal_with_empty_stdout():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "empty.csv")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")
        status, out, err = run_main(["summary.py", path])
    assert status == 1
    assert out == ""
    assert "empty" in err.lower()


def unit_main_valid_file_returns_zero_and_the_report():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "sample.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(
                "region,amount\nnorth,100.00\nsouth,50.00\n"
                "north,25.50\neast,10.25\n"
            )
        status, out, err = run_main(["summary.py", path])
    assert status == 0
    assert err == ""
    assert out.splitlines() == [
        "east 10.25 10.25",
        "north 125.50 62.75",
        "south 50.00 50.00",
        "SKIPPED 0",
        "TOTAL 185.75 4",
    ]


TESTS = [
    ("unit_parse_region_trims_every_ascii_whitespace_character", unit_parse_region_trims_every_ascii_whitespace_character),
    ("unit_parse_region_keeps_internal_spacing", unit_parse_region_keeps_internal_spacing),
    ("unit_parse_region_is_case_sensitive", unit_parse_region_is_case_sensitive),
    ("unit_parse_region_returns_none_for_blank_cells", unit_parse_region_returns_none_for_blank_cells),
    ("unit_parse_region_does_not_trim_non_ascii_whitespace", unit_parse_region_does_not_trim_non_ascii_whitespace),
    ("unit_parse_amount_accepts_plain_decimals_exactly", unit_parse_amount_accepts_plain_decimals_exactly),
    ("unit_parse_amount_rejects_unreadable_cells", unit_parse_amount_rejects_unreadable_cells),
    ("unit_parse_amount_keeps_negative_and_zero_as_valid_measures", unit_parse_amount_keeps_negative_and_zero_as_valid_measures),
    ("unit_parse_amount_never_uses_binary_floats", unit_parse_amount_never_uses_binary_floats),
    ("unit_round_cents_rounds_an_exact_half_away_from_zero", unit_round_cents_rounds_an_exact_half_away_from_zero),
    ("unit_round_cents_rounds_non_halves_by_nearest", unit_round_cents_rounds_non_halves_by_nearest),
    ("unit_round_cents_has_no_negative_zero", unit_round_cents_has_no_negative_zero),
    ("unit_round_cents_handles_large_and_fractional_values", unit_round_cents_handles_large_and_fractional_values),
    ("unit_format_cents_prints_exactly_two_decimals", unit_format_cents_prints_exactly_two_decimals),
    ("unit_format_value_composes_rounding_and_formatting", unit_format_value_composes_rounding_and_formatting),
    ("unit_format_value_always_matches_the_declared_shape", unit_format_value_always_matches_the_declared_shape),
    ("unit_header_columns_resolves_the_declared_order", unit_header_columns_resolves_the_declared_order),
    ("unit_header_columns_resolves_swapped_columns", unit_header_columns_resolves_swapped_columns),
    ("unit_header_columns_ignores_extra_columns", unit_header_columns_ignores_extra_columns),
    ("unit_header_columns_trims_and_folds_names", unit_header_columns_trims_and_folds_names),
    ("unit_header_columns_uses_the_first_matching_column", unit_header_columns_uses_the_first_matching_column),
    ("unit_header_columns_missing_region_is_fatal", unit_header_columns_missing_region_is_fatal),
    ("unit_header_columns_missing_amount_is_fatal", unit_header_columns_missing_amount_is_fatal),
    ("unit_header_columns_missing_both_names_both", unit_header_columns_missing_both_names_both),
    ("unit_header_columns_rejects_an_unparsable_header", unit_header_columns_rejects_an_unparsable_header),
    ("unit_read_records_yields_plain_rows", unit_read_records_yields_plain_rows),
    ("unit_read_records_handles_crlf_and_quoted_commas", unit_read_records_handles_crlf_and_quoted_commas),
    ("unit_read_records_turns_an_unparsable_record_into_the_malformed_sentinel", unit_read_records_turns_an_unparsable_record_into_the_malformed_sentinel),
    ("unit_summarise_declared_sample_is_exact", unit_summarise_declared_sample_is_exact),
    ("unit_summarise_header_only_is_an_empty_report", unit_summarise_header_only_is_an_empty_report),
    ("unit_summarise_rejects_an_empty_file", unit_summarise_rejects_an_empty_file),
    ("unit_summarise_merges_every_duplicate_occurrence", unit_summarise_merges_every_duplicate_occurrence),
    ("unit_summarise_three_valid_two_malformed", unit_summarise_three_valid_two_malformed),
    ("unit_summarise_all_malformed_counts_each_row_once", unit_summarise_all_malformed_counts_each_row_once),
    ("unit_summarise_wrong_field_count_is_malformed", unit_summarise_wrong_field_count_is_malformed),
    ("unit_summarise_blank_region_is_malformed", unit_summarise_blank_region_is_malformed),
    ("unit_summarise_non_decimal_amount_is_malformed", unit_summarise_non_decimal_amount_is_malformed),
    ("unit_summarise_region_key_is_trimmed_and_case_sensitive", unit_summarise_region_key_is_trimmed_and_case_sensitive),
    ("unit_summarise_sorts_region_lines_by_utf8_bytes", unit_summarise_sorts_region_lines_by_utf8_bytes),
    ("unit_summarise_total_revenue_is_the_sum_of_printed_region_revenues", unit_summarise_total_revenue_is_the_sum_of_printed_region_revenues),
    ("unit_summarise_total_orders_is_the_sum_of_region_counts", unit_summarise_total_orders_is_the_sum_of_region_counts),
    ("unit_summarise_average_uses_the_unrounded_sum", unit_summarise_average_uses_the_unrounded_sum),
    ("unit_summarise_negative_values_stay_valid_and_format_with_a_sign", unit_summarise_negative_values_stay_valid_and_format_with_a_sign),
    ("unit_summarise_zero_amounts_are_valid_orders", unit_summarise_zero_amounts_are_valid_orders),
    ("unit_summarise_never_prints_negative_zero", unit_summarise_never_prints_negative_zero),
    ("unit_summarise_prints_exactly_one_skipped_and_one_total_line", unit_summarise_prints_exactly_one_skipped_and_one_total_line),
    ("unit_main_requires_exactly_one_argument", unit_main_requires_exactly_one_argument),
    ("unit_main_missing_path_is_fatal_with_empty_stdout", unit_main_missing_path_is_fatal_with_empty_stdout),
    ("unit_main_empty_file_is_fatal_with_empty_stdout", unit_main_empty_file_is_fatal_with_empty_stdout),
    ("unit_main_valid_file_returns_zero_and_the_report", unit_main_valid_file_returns_zero_and_the_report),
]


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
    for name, function in TESTS:
        check(name, function)
    return emit_tap()


if __name__ == "__main__":
    sys.exit(main())
