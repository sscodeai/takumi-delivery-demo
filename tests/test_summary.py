#!/usr/bin/env python3
"""Acceptance tests for the ticket summary entry point.

Every check drives the real ``bash summary.sh <csv>`` command in a
subprocess against the checked-in fixtures under ``tests/fixtures/``, so the
suite exercises exactly what the delivery declares.  The report is TAP, written
to ``reports/tests.tap`` (or ``$TAP_OUT``), and the runner exits non-zero when
any check fails.

Coverage required by docs/requirements/intake.yaml:
  REQ-001  entry point, argument handling, input left untouched
  REQ-002  header excluded, every accepted row counted once
  REQ-003  per-assignee open/closed counts, including the zero-count case
  REQ-004  exactly one totals line, equal to the per-assignee sums
  AMB-001  one line per assignee carrying both counts
  AMB-002  alphabetical, locale-independent byte order
  AMB-003  only the exact lowercase tokens ``open`` and ``closed``
  AMB-004  an unusable row is skipped without affecting either count
  AMB-005  a missing category is printed as 0
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "summary.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

MIXED_REPORT = "alice 2 1\nbob 0 3\ncarol 1 0\nTOTAL 3 4\n"
ZERO_REPORT = "dave 3 0\nerin 0 1\nTOTAL 3 1\n"
SKIPPED_REPORT = "frank 1 1\nTOTAL 1 1\n"
SORTED_REPORT = (
    "Alice 1 0\nZoe 1 0\nalice 0 1\nbob 0 1\nzoe 1 0\nTOTAL 3 2\n"
)


def run_tool(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SUMMARY), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def report_for(name: str) -> str:
    path = FIXTURES / name
    result = run_tool(str(path))
    assert result.returncode == 0, (
        f"bash summary.sh {path} exited {result.returncode}: {result.stderr}"
    )
    return result.stdout


def report_lines(name: str) -> List[str]:
    return report_for(name).splitlines()


def parse_assignee_line(line: str) -> Tuple[str, int, int]:
    assignee, opened, closed = line.rsplit(" ", 2)
    return assignee, int(opened), int(closed)


def totals_line(lines: List[str]) -> str:
    totals = [line for line in lines if line.startswith("TOTAL ")]
    assert len(totals) == 1, f"expected exactly one TOTAL line, saw {totals!r}"
    return totals[0]


def assignee_lines(lines: List[str]) -> List[str]:
    return [line for line in lines if not line.startswith("TOTAL ")]


# --- REQ-001: entry point -------------------------------------------------


def test_entry_point_sits_at_the_repository_root() -> None:
    assert SUMMARY.is_file(), "summary.sh is missing from the repository root"
    assert (ROOT / "run-tests.sh").is_file(), "run-tests.sh is missing"
    assert (ROOT / "tests" / "mutation.sh").is_file(), "tests/mutation.sh is missing"


def test_first_argument_is_the_csv_path_and_exit_is_zero() -> None:
    assert report_for("mixed.csv") == MIXED_REPORT


def test_relative_path_works_from_the_repository_root() -> None:
    result = subprocess.run(
        ["bash", "summary.sh", "tests/fixtures/mixed.csv"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == MIXED_REPORT


def test_input_file_is_not_modified() -> None:
    path = FIXTURES / "mixed.csv"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    run_tool(str(path))
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after, "summary.sh modified its input file"


def test_missing_argument_is_a_usage_error() -> None:
    result = subprocess.run(
        ["bash", str(SUMMARY)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "a missing CSV argument must be an error"
    assert result.stdout == "", "a usage error must not print a report"


def test_nonexistent_input_is_an_error_with_empty_stdout() -> None:
    result = run_tool(str(FIXTURES / "does-not-exist.csv"))
    assert result.returncode != 0, "a missing input file must be an error"
    assert result.stdout == "", "a failed run must not print a report"


# --- REQ-002 / AMB-003 / AMB-004: parsing ----------------------------------


def test_header_line_is_recognised_and_not_counted() -> None:
    lines = report_lines("mixed.csv")
    assert totals_line(lines) == "TOTAL 3 4"
    names = [parse_assignee_line(line)[0] for line in assignee_lines(lines)]
    assert "assignee" not in names, "the header line was counted as a ticket"
    counted = sum(
        opened + closed
        for _, opened, closed in map(parse_assignee_line, assignee_lines(lines))
    )
    assert counted == 7, f"expected 7 accepted rows from the 7 data rows, got {counted}"


def test_header_only_file_reports_zero_totals() -> None:
    assert report_for("header_only.csv") == "TOTAL 0 0\n"


def test_every_accepted_row_is_counted_exactly_once() -> None:
    _, opened, closed = parse_assignee_line(totals_line(report_lines("mixed.csv")))
    data_rows = len((FIXTURES / "mixed.csv").read_text().splitlines()) - 1
    assert opened + closed == data_rows


def test_unusable_rows_are_skipped_without_affecting_counts() -> None:
    # skipped.csv: valid `frank` rows are open+closed; the empty assignees,
    # the `grace,pending` status, the capitalised `Open`, the leading-blank
    # status, the short row and the empty status are all ignored.
    assert report_for("skipped.csv") == SKIPPED_REPORT


def test_only_exact_lowercase_status_tokens_are_recognised() -> None:
    lines = report_lines("skipped.csv")
    assert totals_line(lines) == "TOTAL 1 1"
    names = [parse_assignee_line(line)[0] for line in assignee_lines(lines)]
    assert names == ["frank"], f"unusable rows leaked into the report: {names!r}"


# --- REQ-003 / AMB-001 / AMB-005: per-assignee lines -----------------------


def test_mixed_per_assignee_open_and_closed_counts() -> None:
    lines = report_lines("mixed.csv")
    parsed = [parse_assignee_line(line) for line in assignee_lines(lines)]
    assert ("alice", 2, 1) in parsed
    assert ("bob", 0, 3) in parsed
    assert ("carol", 1, 0) in parsed


def test_each_assignee_appears_on_exactly_one_line() -> None:
    lines = report_lines("mixed.csv")
    names = [parse_assignee_line(line)[0] for line in assignee_lines(lines)]
    assert names == ["alice", "bob", "carol"]
    assert len(names) == len(set(names)), "an assignee was reported twice"


def test_assignee_with_one_status_still_prints_both_counts() -> None:
    # AMB-005: dave is all-open and erin all-closed; the missing count is 0.
    assert report_for("zero.csv") == ZERO_REPORT


# --- REQ-004: totals line --------------------------------------------------


def test_exactly_one_totals_line() -> None:
    lines = report_lines("mixed.csv")
    totals = [line for line in lines if line.startswith("TOTAL ")]
    assert len(totals) == 1, f"expected exactly one totals line, saw {totals!r}"


def test_totals_equal_the_sum_of_per_assignee_counts() -> None:
    lines = report_lines("mixed.csv")
    parsed = [parse_assignee_line(line) for line in assignee_lines(lines)]
    _, open_total, closed_total = parse_assignee_line(totals_line(lines))
    assert open_total == sum(opened for _, opened, _ in parsed)
    assert closed_total == sum(closed for _, _, closed in parsed)


def test_totals_are_correct_on_the_zero_count_fixture() -> None:
    _, open_total, closed_total = parse_assignee_line(
        totals_line(report_lines("zero.csv"))
    )
    assert (open_total, closed_total) == (3, 1)


# --- AMB-002: ordering -----------------------------------------------------


def test_assignees_are_sorted_by_locale_independent_bytes() -> None:
    # ASCII bytes order `A` < `Z` < `a` < `b` < `z`, so case is significant
    # and the layout does not depend on the CSV row order.
    assert report_for("sorting.csv") == SORTED_REPORT


def test_report_order_does_not_depend_on_row_order() -> None:
    sorted_lines = report_lines("sorting.csv")
    reversed_fixture = FIXTURES / "sorting-reversed.csv"
    rows = (FIXTURES / "sorting.csv").read_text().splitlines()
    reversed_fixture.write_text(
        "\n".join([rows[0], *reversed(rows[1:])]) + "\n", encoding="utf-8"
    )
    try:
        assert report_lines("sorting-reversed.csv") == sorted_lines
    finally:
        reversed_fixture.unlink()


TESTS = [
    test_entry_point_sits_at_the_repository_root,
    test_first_argument_is_the_csv_path_and_exit_is_zero,
    test_relative_path_works_from_the_repository_root,
    test_input_file_is_not_modified,
    test_missing_argument_is_a_usage_error,
    test_nonexistent_input_is_an_error_with_empty_stdout,
    test_header_line_is_recognised_and_not_counted,
    test_header_only_file_reports_zero_totals,
    test_every_accepted_row_is_counted_exactly_once,
    test_unusable_rows_are_skipped_without_affecting_counts,
    test_only_exact_lowercase_status_tokens_are_recognised,
    test_mixed_per_assignee_open_and_closed_counts,
    test_each_assignee_appears_on_exactly_one_line,
    test_assignee_with_one_status_still_prints_both_counts,
    test_exactly_one_totals_line,
    test_totals_equal_the_sum_of_per_assignee_counts,
    test_totals_are_correct_on_the_zero_count_fixture,
    test_assignees_are_sorted_by_locale_independent_bytes,
    test_report_order_does_not_depend_on_row_order,
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

    out_lines = ["TAP version 13"]
    for number, (name, passed, detail) in enumerate(results, start=1):
        out_lines.append(("ok" if passed else "not ok") + f" {number} - {name}")
        if not passed:
            for detail_line in detail.splitlines():
                out_lines.append(f"  # {detail_line}")
    out_lines.append(f"1..{len(results)}")
    passed_count = sum(1 for _, passed, _ in results if passed)
    out_lines.append(f"# tests {len(results)}")
    out_lines.append(f"# pass {passed_count}")
    out_lines.append(f"# fail {len(results) - passed_count}")
    text = "\n".join(out_lines) + "\n"

    tap_path = Path(os.environ.get("TAP_OUT", "reports/tests.tap"))
    if not tap_path.is_absolute():
        tap_path = ROOT / tap_path
    tap_path.parent.mkdir(parents=True, exist_ok=True)
    tap_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
