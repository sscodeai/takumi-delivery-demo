#!/usr/bin/env python3
"""Unit tests for the functions behind ``bash summary.sh``.

These checks import ``summary.py`` directly and exercise one function at a time.
They are deliberately separate from ``tests/test_summary.py`` (which drives the
real entry point in subprocesses): together the two files form the delivered
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


# --- REQ-002: the header is exactly region,amount in that order ---------------


def unit_locate_header_accepts_the_declared_header():
    assert summary.locate_header(["region", "amount"]) is None


def unit_locate_header_trims_blanks_and_ignores_case():
    assert summary.locate_header([" Region ", " AMOUNT\t"]) is None


def unit_locate_header_rejects_the_wrong_order():
    try:
        summary.locate_header(["amount", "region"])
    except summary.HeaderError:
        return
    raise AssertionError("amount,region must not be accepted")


def unit_locate_header_rejects_other_or_extra_columns():
    for record in (
        ["region", "total"],
        ["region", "amount", "note"],
        ["region"],
        ["region", "amount", ""],
        [],
    ):
        try:
            summary.locate_header(record)
        except summary.HeaderError:
            continue
        raise AssertionError("%r must not be accepted as the header" % (record,))


def unit_locate_header_rejects_a_missing_header():
    try:
        summary.locate_header(summary.MALFORMED)
    except summary.HeaderError:
        return
    raise AssertionError("an unreadable first record is not a header")


# --- REQ-005: an amount is a plain decimal -----------------------------------


def unit_parse_amount_accepts_plain_decimals():
    assert summary.parse_amount("1") == Fraction(1)
    assert summary.parse_amount("120.50") == Fraction(241, 2)
    assert summary.parse_amount("1.5") == Fraction(3, 2)
    assert summary.parse_amount("+1.5") == Fraction(3, 2)
    assert summary.parse_amount("-10.00") == Fraction(-10)
    assert summary.parse_amount("007") == Fraction(7)
    assert summary.parse_amount("0.00") == Fraction(0)


def unit_parse_amount_rejects_everything_else():
    for text in (
        "",
        "abc",
        "1e3",
        "1E3",
        "$5",
        "1,000",
        "5.",
        ".5",
        " 5",
        "5 ",
        "1_000",
        "NaN",
        "Infinity",
        "--1",
        "+",
        "-",
        "0x10",
    ):
        assert summary.parse_amount(text) is None, text


# --- AMB-003 / REQ-007: money is two decimals, half away from zero ----------


def unit_format_money_rounds_an_exact_half_away_from_zero():
    assert summary.format_money(Fraction("1.005")) == "1.01"
    assert summary.format_money(Fraction("2.005")) == "2.01"
    assert summary.format_money(Fraction("1.015")) == "1.02"
    assert summary.format_money(Fraction("99.995")) == "100.00"


def unit_format_money_rounds_negative_halves_away_from_zero():
    assert summary.format_money(Fraction("-1.005")) == "-1.01"
    assert summary.format_money(Fraction("-2.005")) == "-2.01"


def unit_format_money_truncates_below_a_half():
    assert summary.format_money(Fraction("1.004")) == "1.00"
    assert summary.format_money(Fraction("-1.004")) == "-1.00"
    assert summary.format_money(Fraction(1, 3)) == "0.33"


def unit_format_money_always_prints_two_decimals():
    assert summary.format_money(Fraction(0)) == "0.00"
    assert summary.format_money(Fraction(5)) == "5.00"
    assert summary.format_money(Fraction(100)) == "100.00"
    assert summary.format_money(Fraction(-3, 2)) == "-1.50"


def unit_format_money_never_prints_a_negative_zero():
    assert summary.format_money(Fraction(0)) == "0.00"
    assert summary.format_money(Fraction("-0.00")) == "0.00"
    assert summary.format_money(Fraction(-1, 1000)) == "0.00"


# --- REQ-003 / REQ-005: a row is accepted or malformed -----------------------


def unit_parse_row_accepts_a_region_and_plain_amount():
    assert summary.parse_row(["north", "120.50"]) == (
        "north",
        Fraction(241, 2),
    )


def unit_parse_row_trims_the_region():
    assert summary.parse_row(["  north\t", "1"]) == ("north", Fraction(1))


def unit_parse_row_keeps_region_case_and_inner_spaces():
    assert summary.parse_row(["North East", "1"]) == ("North East", Fraction(1))
    assert summary.parse_row(["North", "1"])[0] == "North"


def unit_parse_row_skips_every_malformed_row():
    for record in (
        ["north"],  # one field
        ["north", "1", "extra"],  # three fields
        [],  # blank line
        ["", "1"],  # empty region
        ["   ", "1"],  # blank region after trimming
        ["north", ""],  # empty amount
        ["north", "abc"],  # non-numeric amount
        ["north", "1e3"],  # exponent notation
        ["north", "$5"],  # currency symbol
        ["north", "1,000"],  # thousands separator
        ["north", " 5"],  # surrounding blank is not a plain decimal
        summary.MALFORMED,  # the csv parser rejected the record
    ):
        assert summary.parse_row(record) is None, record


# --- REQ-003 / REQ-004 / REQ-005 / REQ-009: aggregation ---------------------


SAMPLE = [
    ["region", "amount"],
    ["north", "120.50"],
    ["south", "80.00"],
    ["north", "99.50"],
    ["east", "45.25"],
]


def unit_summarise_groups_sorts_and_prints_the_sample():
    assert summary.summarise(SAMPLE) == [
        "east 1 45.25 45.25",
        "north 2 220.00 110.00",
        "south 1 80.00 80.00",
        "TOTAL 4 345.25",
        "SKIPPED 0",
    ]


def unit_summarise_keeps_every_duplicate_row():
    records = [["region", "amount"], ["south", "50.00"], ["south", "50.00"]]
    assert summary.summarise(records) == [
        "south 2 100.00 50.00",
        "TOTAL 2 100.00",
        "SKIPPED 0",
    ]


def unit_summarise_counts_malformed_rows_without_aggregating_them():
    records = [
        ["region", "amount"],
        ["north", "100"],
        ["north", "abc"],
        ["", "5"],
        ["north", "1", "extra"],
        summary.MALFORMED,
        ["south", "10"],
    ]
    assert summary.summarise(records) == [
        "north 1 100.00 100.00",
        "south 1 10.00 10.00",
        "TOTAL 2 110.00",
        "SKIPPED 4",
    ]


def unit_summarise_reports_an_empty_report_for_a_header_only_file():
    assert summary.summarise([["region", "amount"]]) == [
        "TOTAL 0 0.00",
        "SKIPPED 0",
    ]


def unit_summarise_requires_a_header():
    for records in ([], [summary.MALFORMED], [["north", "1"]]):
        try:
            summary.summarise(records)
        except summary.HeaderError:
            continue
        raise AssertionError("%r must be a fatal header error" % (records,))


# --- the csv reader turns parser errors into malformed rows ------------------


def unit_read_records_yields_every_csv_record():
    handle = io.StringIO("region,amount\nnorth,1\n\nsouth,2\n")
    assert list(summary.read_records(handle)) == [
        ["region", "amount"],
        ["north", "1"],
        [],
        ["south", "2"],
    ]


def unit_read_records_turns_a_csv_error_into_a_malformed_record():
    class BrokenReader:
        def __init__(self):
            self.step = 0

        def __iter__(self):
            return self

        def __next__(self):
            self.step += 1
            if self.step == 1:
                return ["region", "amount"]
            if self.step == 2:
                raise csv.Error("malformed record")
            raise StopIteration

    original = summary.csv.reader
    try:
        summary.csv.reader = lambda handle, **kwargs: BrokenReader()
        records = list(summary.read_records(io.StringIO("")))
    finally:
        summary.csv.reader = original
    assert records[0] == ["region", "amount"]
    assert records[1] is summary.MALFORMED
    assert len(records) == 2


# --- REQ-001: the module-level entry point -----------------------------------


def unit_main_rejects_a_wrong_argument_count():
    for argv in (["summary.py"], ["summary.py", "a.csv", "stray"]):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = summary.main(argv)
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


def unit_main_stops_on_a_missing_or_wrong_header():
    for text in ("", "north,1\n"):
        with tempfile.TemporaryDirectory(prefix="summary-unit-") as directory:
            path = os.path.join(directory, "input.csv")
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = summary.main(["summary.py", path])
        assert status == 1, status
        assert out.getvalue() == "", out.getvalue()
        assert err.getvalue().strip(), "a diagnostic on stderr is expected"


def unit_main_stops_on_a_permission_denied_input():
    # REQ-001: a file that exists but cannot be read is a stop error, like a
    # missing file. chmod is unreliable under a root test runner, so raise the
    # operating-system error that open() would raise instead.
    path = os.path.join(tempfile.gettempdir(), "summary-unreadable.csv")
    out, err = io.StringIO(), io.StringIO()

    def denied(*args, **kwargs):
        raise PermissionError(13, "Permission denied", path)

    summary.open = denied
    try:
        with redirect_stdout(out), redirect_stderr(err):
            status = summary.main(["summary.py", path])
    finally:
        del summary.open
    assert status == 1, status
    assert out.getvalue() == "", out.getvalue()
    assert "cannot read" in err.getvalue(), err.getvalue()


def unit_main_writes_the_report_to_stdout():
    with tempfile.TemporaryDirectory(prefix="summary-unit-") as directory:
        path = os.path.join(directory, "input.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write("region,amount\nnorth,1.00\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = summary.main(["summary.py", path])
    assert status == 0, status
    assert out.getvalue() == "north 1 1.00 1.00\nTOTAL 1 1.00\nSKIPPED 0\n", out.getvalue()
    assert err.getvalue() == "", err.getvalue()


def unit_parse_row_accepts_zero_and_negative_amounts():
    assert summary.parse_row(["east", "0.00"]) == ("east", Fraction(0))
    assert summary.parse_row(["east", "-10.00"]) == ("east", Fraction(-10))


def unit_parse_row_rejects_three_fields_even_when_the_third_is_blank():
    assert summary.parse_row(["north", "1", ""]) is None


def unit_format_money_rounds_a_carry_into_the_whole():
    assert summary.format_money(Fraction("0.995")) == "1.00"
    assert summary.format_money(Fraction("-0.995")) == "-1.00"


def unit_format_money_keeps_large_values_exact():
    assert summary.format_money(Fraction("123456789.125")) == "123456789.13"
    assert summary.format_money(Fraction("123456789.124")) == "123456789.12"


def unit_summarise_sorts_regions_rather_than_keeping_input_order():
    records = [
        ["region", "amount"],
        ["zulu", "1"],
        ["Alpha", "2"],
        ["mike", "3"],
    ]
    out = summary.summarise(records)
    assert [line.split(" ")[0] for line in out[:-2]] == ["Alpha", "mike", "zulu"], out


def unit_summarise_prints_total_then_skipped():
    records = [["region", "amount"], ["a", "1"], ["b", "bad"]]
    out = summary.summarise(records)
    assert out[-2].startswith("TOTAL "), out
    assert out[-1] == "SKIPPED 1", out


def unit_summarise_mean_uses_the_exact_sum():
    # Exact sum 1.005 prints as 1.01, but the mean is 0.5025 -> 0.50. Rounding
    # the printed sum again would print 0.51, so this pins exact arithmetic.
    records = [["region", "amount"], ["x", "1.005"], ["x", "0"]]
    assert summary.summarise(records) == [
        "x 2 1.01 0.50",
        "TOTAL 2 1.01",
        "SKIPPED 0",
    ]


def unit_summarise_accepts_zero_and_negative_amounts():
    records = [
        ["region", "amount"],
        ["east", "-10.00"],
        ["east", "30.00"],
        ["west", "0.00"],
    ]
    assert summary.summarise(records) == [
        "east 2 20.00 10.00",
        "west 1 0.00 0.00",
        "TOTAL 3 20.00",
        "SKIPPED 0",
    ]


def unit_read_records_yields_nothing_for_an_empty_handle():
    assert list(summary.read_records(io.StringIO(""))) == []


def unit_read_records_turns_an_unclosed_quote_into_a_malformed_record():
    # RFC 4180 requires the closing quote, so this is one unparsable data row
    # (AMB-001), not an amount that happens to be "100.00".
    records = list(summary.read_records(io.StringIO('region,amount\nnorth,"100.00')))
    assert records[0] == ["region", "amount"]
    assert records[1] is summary.MALFORMED
    assert len(records) == 2, records


UNIT_TESTS = [
    ("unit_locate_header_accepts_the_declared_header", unit_locate_header_accepts_the_declared_header),
    ("unit_locate_header_trims_blanks_and_ignores_case", unit_locate_header_trims_blanks_and_ignores_case),
    ("unit_locate_header_rejects_the_wrong_order", unit_locate_header_rejects_the_wrong_order),
    ("unit_locate_header_rejects_other_or_extra_columns", unit_locate_header_rejects_other_or_extra_columns),
    ("unit_locate_header_rejects_a_missing_header", unit_locate_header_rejects_a_missing_header),
    ("unit_parse_amount_accepts_plain_decimals", unit_parse_amount_accepts_plain_decimals),
    ("unit_parse_amount_rejects_everything_else", unit_parse_amount_rejects_everything_else),
    ("unit_format_money_rounds_an_exact_half_away_from_zero", unit_format_money_rounds_an_exact_half_away_from_zero),
    ("unit_format_money_rounds_negative_halves_away_from_zero", unit_format_money_rounds_negative_halves_away_from_zero),
    ("unit_format_money_truncates_below_a_half", unit_format_money_truncates_below_a_half),
    ("unit_format_money_always_prints_two_decimals", unit_format_money_always_prints_two_decimals),
    ("unit_format_money_never_prints_a_negative_zero", unit_format_money_never_prints_a_negative_zero),
    ("unit_parse_row_accepts_a_region_and_plain_amount", unit_parse_row_accepts_a_region_and_plain_amount),
    ("unit_parse_row_trims_the_region", unit_parse_row_trims_the_region),
    ("unit_parse_row_keeps_region_case_and_inner_spaces", unit_parse_row_keeps_region_case_and_inner_spaces),
    ("unit_parse_row_skips_every_malformed_row", unit_parse_row_skips_every_malformed_row),
    ("unit_parse_row_accepts_zero_and_negative_amounts", unit_parse_row_accepts_zero_and_negative_amounts),
    ("unit_parse_row_rejects_three_fields_even_when_the_third_is_blank", unit_parse_row_rejects_three_fields_even_when_the_third_is_blank),
    ("unit_format_money_rounds_a_carry_into_the_whole", unit_format_money_rounds_a_carry_into_the_whole),
    ("unit_format_money_keeps_large_values_exact", unit_format_money_keeps_large_values_exact),
    ("unit_summarise_sorts_regions_rather_than_keeping_input_order", unit_summarise_sorts_regions_rather_than_keeping_input_order),
    ("unit_summarise_prints_total_then_skipped", unit_summarise_prints_total_then_skipped),
    ("unit_summarise_mean_uses_the_exact_sum", unit_summarise_mean_uses_the_exact_sum),
    ("unit_summarise_accepts_zero_and_negative_amounts", unit_summarise_accepts_zero_and_negative_amounts),
    ("unit_read_records_yields_nothing_for_an_empty_handle", unit_read_records_yields_nothing_for_an_empty_handle),
    ("unit_read_records_turns_an_unclosed_quote_into_a_malformed_record", unit_read_records_turns_an_unclosed_quote_into_a_malformed_record),
    ("unit_summarise_groups_sorts_and_prints_the_sample", unit_summarise_groups_sorts_and_prints_the_sample),
    ("unit_summarise_keeps_every_duplicate_row", unit_summarise_keeps_every_duplicate_row),
    ("unit_summarise_counts_malformed_rows_without_aggregating_them", unit_summarise_counts_malformed_rows_without_aggregating_them),
    ("unit_summarise_reports_an_empty_report_for_a_header_only_file", unit_summarise_reports_an_empty_report_for_a_header_only_file),
    ("unit_summarise_requires_a_header", unit_summarise_requires_a_header),
    ("unit_read_records_yields_every_csv_record", unit_read_records_yields_every_csv_record),
    ("unit_read_records_turns_a_csv_error_into_a_malformed_record", unit_read_records_turns_a_csv_error_into_a_malformed_record),
    ("unit_main_rejects_a_wrong_argument_count", unit_main_rejects_a_wrong_argument_count),
    ("unit_main_stops_on_unreadable_input", unit_main_stops_on_unreadable_input),
    ("unit_main_stops_on_a_permission_denied_input", unit_main_stops_on_a_permission_denied_input),
    ("unit_main_stops_on_a_missing_or_wrong_header", unit_main_stops_on_a_missing_or_wrong_header),
    ("unit_main_writes_the_report_to_stdout", unit_main_writes_the_report_to_stdout),
]
