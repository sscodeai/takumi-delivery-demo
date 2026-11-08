#!/usr/bin/env python3
"""Unit tests for the rules behind the ticket summary.

These import ``summary.py`` directly and pin the helpers the CLI composes:
header resolution, assignee normalisation, status classification, the skip
accounting and the report layout.  The TAP report is written to
``reports/tests-units.tap`` (or ``$TAP_OUT``).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _tap import ROOT, run_tests  # noqa: E402  (path is set up above)
import summary  # noqa: E402  (path is set up above)


def test_resolve_columns_reads_the_declared_order() -> None:
    assert summary.resolve_columns(["assignee", "status"]) == (0, 1)


def test_resolve_columns_follows_names_not_positions() -> None:
    assert summary.resolve_columns(["status", "assignee"]) == (1, 0)
    assert summary.resolve_columns(["id", "assignee", "status", "x"]) == (1, 2)


def test_resolve_columns_normalises_the_header_cell() -> None:
    assert summary.resolve_columns([" Assignee ", "STATUS"]) == (0, 1)
    assert summary.resolve_columns(["\ufeffassignee", "status"]) == (0, 1)


def test_resolve_columns_rejects_a_missing_column() -> None:
    for header in (["assignee"], ["status"], ["id", "state"], []):
        try:
            summary.resolve_columns(header)
        except summary.InputError:
            continue
        raise AssertionError(f"header {header!r} should be rejected")


def test_classify_status_trims_and_folds_case() -> None:
    assert summary.classify_status("open") == "open"
    assert summary.classify_status(" OPEN ") == "open"
    assert summary.classify_status("Closed") == "closed"
    assert summary.classify_status("closed\t") == "closed"


def test_classify_status_rejects_anything_else() -> None:
    for value in ("pending", "", "   ", "openx", "closedish", "re-opened"):
        assert summary.classify_status(value) is None, value


def test_normalise_assignee_trims_but_keeps_case() -> None:
    assert summary.normalise_assignee("  Alice \t") == "Alice"
    assert summary.normalise_assignee("alice") == "alice"
    assert summary.normalise_assignee("Alice") != summary.normalise_assignee("alice")


def test_summarise_records_counts_both_statuses() -> None:
    counts, skipped = summary.summarise_records(
        ["assignee", "status"],
        [
            ["alice", "open"],
            ["alice", "closed"],
            ["bob", "closed"],
        ],
    )
    assert counts == {"alice": [1, 1], "bob": [0, 1]}
    assert skipped == 0


def test_summarise_records_skips_every_malformed_row() -> None:
    counts, skipped = summary.summarise_records(
        ["assignee", "status"],
        [
            ["alice", "open"],
            [" alice ", " CLOSED "],
            ["", "open"],
            ["bob", ""],
            ["carol", "pending"],
            ["dave"],
        ],
    )
    assert counts == {"alice": [1, 1]}
    assert skipped == 4


def test_summarise_records_honours_named_column_order() -> None:
    counts, skipped = summary.summarise_records(
        ["status", "assignee"],
        [["open", "alice"], ["closed", "alice"]],
    )
    assert counts == {"alice": [1, 1]}
    assert skipped == 0


def test_summarise_records_counts_each_row_once() -> None:
    counts, skipped = summary.summarise_records(
        ["assignee", "status"],
        [["ann", "open"], ["ann", "open"], ["ann", "closed"]],
    )
    assert counts == {"ann": [2, 1]}
    assert skipped == 0
    assert sum(counts["ann"]) == 3


def test_format_report_sorts_by_utf8_bytes_and_prints_both_counts() -> None:
    counts = {"zoe": [1, 0], "Alice": [1, 0], "alice": [0, 1], "Bob": [0, 1]}
    assert summary.format_report(counts) == [
        "Alice 1 0",
        "Bob 0 1",
        "alice 0 1",
        "zoe 1 0",
    ]


def test_format_report_of_no_counts_is_empty() -> None:
    assert summary.format_report({}) == []


def test_summarise_file_accepts_a_utf8_bom() -> None:
    handle = tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False)
    with handle:
        handle.write(b"\xef\xbb\xbfassignee,status\nann,open\n")
    path = handle.name
    try:
        counts, skipped = summary.summarise_file(path)
    finally:
        os.unlink(path)
    assert counts == {"ann": [1, 0]}
    assert skipped == 0


def test_summarise_file_rejects_an_empty_file() -> None:
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    path = handle.name
    handle.close()
    try:
        try:
            summary.summarise_file(path)
        except summary.InputError:
            return
        raise AssertionError("an empty file should be an InputError")
    finally:
        os.unlink(path)


def test_summarise_file_rejects_a_missing_file() -> None:
    try:
        summary.summarise_file(str(ROOT / "tests" / "fixtures" / "absent.csv"))
    except summary.InputError:
        return
    raise AssertionError("a missing file should be an InputError")


TESTS = [
    test_resolve_columns_reads_the_declared_order,
    test_resolve_columns_follows_names_not_positions,
    test_resolve_columns_normalises_the_header_cell,
    test_resolve_columns_rejects_a_missing_column,
    test_classify_status_trims_and_folds_case,
    test_classify_status_rejects_anything_else,
    test_normalise_assignee_trims_but_keeps_case,
    test_summarise_records_counts_both_statuses,
    test_summarise_records_skips_every_malformed_row,
    test_summarise_records_honours_named_column_order,
    test_summarise_records_counts_each_row_once,
    test_format_report_sorts_by_utf8_bytes_and_prints_both_counts,
    test_format_report_of_no_counts_is_empty,
    test_summarise_file_accepts_a_utf8_bom,
    test_summarise_file_rejects_an_empty_file,
    test_summarise_file_rejects_a_missing_file,
]


if __name__ == "__main__":
    sys.exit(run_tests(TESTS, "reports/tests-units.tap"))
