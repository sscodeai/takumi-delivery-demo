#!/usr/bin/env python3
"""Unit tests for the rules behind the ticket summary.

These import ``summary.py`` directly and check the helpers the CLI composes.
The TAP report is written to ``reports/tests-summary-units.tap`` (or
``$TAP_OUT``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import summary  # noqa: E402  (path is set up above)


def test_resolve_columns_reads_the_declared_order() -> None:
    assert summary.resolve_columns(["assignee", "status"]) == (0, 1)


def test_resolve_columns_follows_names_not_positions() -> None:
    assert summary.resolve_columns(["status", "assignee"]) == (1, 0)


def test_resolve_columns_rejects_a_missing_column() -> None:
    for header in (["assignee"], ["status"], ["id", "state"]):
        try:
            summary.resolve_columns(header)
        except summary.InputError:
            continue
        raise AssertionError(f"header {header!r} should be rejected")


def test_summarise_counts_both_statuses_per_assignee() -> None:
    counts = summary.summarise(
        [("alice", "open"), ("alice", "closed"), ("bob", "closed")]
    )
    assert counts == {"alice": [1, 1], "bob": [0, 1]}


def test_summarise_skips_an_empty_assignee() -> None:
    counts = summary.summarise([("", "open"), ("", "closed"), ("ann", "open")])
    assert counts == {"ann": [1, 0]}


def test_summarise_skips_unrecognised_statuses() -> None:
    counts = summary.summarise(
        [
            ("ann", "open"),
            ("ann", "Open"),
            ("ann", "OPEN"),
            ("ann", " open"),
            ("ann", "closed "),
            ("ann", ""),
            ("ann", "pending"),
        ]
    )
    assert counts == {"ann": [1, 0]}


def test_summarise_keeps_a_zero_slot_for_a_single_status_assignee() -> None:
    counts = summary.summarise([("open-only", "open"), ("closed-only", "closed")])
    assert counts["open-only"] == [1, 0]
    assert counts["closed-only"] == [0, 1]


def test_format_report_sorts_by_utf8_bytes() -> None:
    counts = {"zoe": [1, 0], "Alice": [1, 0], "alice": [0, 1], "Bob": [0, 1]}
    lines = summary.format_report(counts)
    assert [line.rsplit(" ", 2)[0] for line in lines[:-1]] == [
        "Alice",
        "Bob",
        "alice",
        "zoe",
    ]


def test_format_report_prints_exactly_one_total_line() -> None:
    lines = summary.format_report({"ann": [2, 3]})
    assert lines == ["ann 2 3", "TOTAL 2 3"]


def test_format_report_of_an_empty_count_is_zero_totals() -> None:
    assert summary.format_report({}) == ["TOTAL 0 0"]


def test_format_report_totals_are_the_sums_of_the_lines() -> None:
    lines = summary.format_report({"ann": [2, 3], "bob": [0, 4]})
    parsed = [line.rsplit(" ", 2) for line in lines[:-1]]
    assert int(lines[-1].rsplit(" ", 2)[1]) == sum(int(p[1]) for p in parsed)
    assert int(lines[-1].rsplit(" ", 2)[2]) == sum(int(p[2]) for p in parsed)


def test_read_rows_skips_a_row_that_is_too_short() -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "skipped.csv"
    rows = summary.read_rows(str(fixture))
    assert ("frank", "open") in rows
    assert all(len(pair) == 2 for pair in rows)


def test_read_rows_rejects_an_empty_file() -> None:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        path = handle.name
    try:
        try:
            summary.read_rows(path)
        except summary.InputError:
            return
        raise AssertionError("an empty file should be an InputError")
    finally:
        os.unlink(path)


def test_read_rows_rejects_a_missing_file() -> None:
    try:
        summary.read_rows(str(ROOT / "tests" / "fixtures" / "absent.csv"))
    except summary.InputError:
        return
    raise AssertionError("a missing file should be an InputError")


def test_read_rows_accepts_a_utf8_bom_header() -> None:
    import tempfile

    with tempfile.NamedTemporaryFile(
        "wb", suffix=".csv", delete=False
    ) as handle:
        handle.write(b"\xef\xbb\xbfassignee,status\nann,open\n")
        path = handle.name
    try:
        assert summary.read_rows(path) == [("ann", "open")]
    finally:
        os.unlink(path)


TESTS = [
    test_resolve_columns_reads_the_declared_order,
    test_resolve_columns_follows_names_not_positions,
    test_resolve_columns_rejects_a_missing_column,
    test_summarise_counts_both_statuses_per_assignee,
    test_summarise_skips_an_empty_assignee,
    test_summarise_skips_unrecognised_statuses,
    test_summarise_keeps_a_zero_slot_for_a_single_status_assignee,
    test_format_report_sorts_by_utf8_bytes,
    test_format_report_prints_exactly_one_total_line,
    test_format_report_of_an_empty_count_is_zero_totals,
    test_format_report_totals_are_the_sums_of_the_lines,
    test_read_rows_skips_a_row_that_is_too_short,
    test_read_rows_rejects_an_empty_file,
    test_read_rows_rejects_a_missing_file,
    test_read_rows_accepts_a_utf8_bom_header,
]


def main() -> int:
    results = []
    for test in TESTS:
        try:
            test()
            results.append((test.__name__, True, ""))
        except Exception as exc:  # noqa: BLE001 - every failure is a TAP result
            detail = str(exc) or exc.__class__.__name__
            results.append((test.__name__, False, detail))

    out = ["TAP version 13"]
    for number, (name, passed, detail) in enumerate(results, start=1):
        out.append(("ok" if passed else "not ok") + f" {number} - {name}")
        if not passed:
            for detail_line in detail.splitlines():
                out.append(f"  # {detail_line}")
    out.append(f"1..{len(results)}")
    passed_count = sum(1 for _, passed, _ in results if passed)
    out.append(f"# tests {len(results)}")
    out.append(f"# pass {passed_count}")
    out.append(f"# fail {len(results) - passed_count}")
    text = "\n".join(out) + "\n"

    tap_path = Path(os.environ.get("TAP_OUT", "reports/tests-summary-units.tap"))
    if not tap_path.is_absolute():
        tap_path = ROOT / tap_path
    tap_path.parent.mkdir(parents=True, exist_ok=True)
    tap_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
