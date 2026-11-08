#!/usr/bin/env python3
"""Unit checks for the functions behind ``bash ticket-summary.sh``.

These checks import ``ticket_summary`` directly and exercise one rule at a time.
Together with ``tests/test_ticket_summary.py`` (which drives the real entry
point in subprocesses) they form the delivered suite; ``bash run-tests.sh`` runs
both through the same TAP harness and writes this report to
``reports/tests-ticket-units.tap`` (override with ``TAP_OUT``).
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ticket_summary  # noqa: E402 - importing the delivery under test

TAP_OUT = os.environ.get(
    "TAP_OUT", os.path.join(ROOT, "reports", "tests-ticket-units.tap")
)

RESULTS = []
SANDBOX = tempfile.mkdtemp(prefix="ticket-unit-")


def check(name, function):
    try:
        function()
    except AssertionError as exc:
        RESULTS.append((False, name, str(exc)))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append((False, name, "%s: %s" % (type(exc).__name__, exc)))
    else:
        RESULTS.append((True, name, ""))


# --- header resolution -------------------------------------------------------


def unit_resolve_columns_reads_declared_positions():
    assert ticket_summary.resolve_columns(["assignee", "status"]) == (0, 1)
    assert ticket_summary.resolve_columns(["status", "assignee"]) == (1, 0)


def unit_resolve_columns_trims_and_folds_header_names():
    assert ticket_summary.resolve_columns([" Assignee ", "STATUS"]) == (0, 1)


def unit_resolve_columns_ignores_extra_columns():
    assert ticket_summary.resolve_columns(["id", "status", "team", "assignee"]) == (3, 1)


def unit_resolve_columns_names_each_missing_column():
    for header, expected in (
        (["assignee"], "status"),
        (["status"], "assignee"),
        (["id"], "assignee, status"),
    ):
        try:
            ticket_summary.resolve_columns(header)
        except ticket_summary.UsageError as exc:
            assert expected in str(exc), (header, str(exc))
        else:
            raise AssertionError("expected a UsageError for %r" % (header,))


# --- status classification (AMB-001) ----------------------------------------


def unit_classify_status_recognises_open_and_closed_ignoring_case_and_blanks():
    assert ticket_summary.classify_status("open") == "open"
    assert ticket_summary.classify_status(" OPEN ") == "open"
    assert ticket_summary.classify_status("Closed") == "closed"


def unit_classify_status_rejects_every_other_value():
    for value in ("pending", "in-progress", "", "   ", "reopened", "closedx"):
        assert ticket_summary.classify_status(value) is None, value


# --- row summarisation (REQ-003..REQ-006, AMB-002..AMB-004) ------------------


def unit_summarise_counts_open_and_closed_per_assignee():
    records = [
        ["assignee", "status"],
        ["alice", "open"],
        ["alice", "closed"],
        ["alice", "open"],
        ["bob", "closed"],
    ]
    counts, skipped = ticket_summary.summarise(records)
    assert counts == {"alice": [2, 1], "bob": [0, 1]}, counts
    assert skipped == 0, skipped


def unit_summarise_skips_every_unusable_shape():
    records = [
        ["assignee", "status"],
        ["alice", "open"],
        ["bob", "closed", "extra"],
        ["carol"],
        ["", "open"],
        ["dave", ""],
        ["erin", "pending"],
        ["frank", " open "],
    ]
    counts, skipped = ticket_summary.summarise(records)
    assert counts == {"alice": [1, 0], "frank": [1, 0]}, counts
    assert skipped == 5, skipped


def unit_summarise_trims_the_assignee_into_the_group_key():
    records = [
        ["assignee", "status"],
        [" alice ", "open"],
        ["alice", "closed"],
    ]
    counts, _ = ticket_summary.summarise(records)
    assert counts == {"alice": [1, 1]}, counts


def unit_summarise_keeps_name_casing_apart():
    records = [
        ["assignee", "status"],
        ["Alice", "open"],
        ["alice", "closed"],
    ]
    counts, _ = ticket_summary.summarise(records)
    assert counts == {"Alice": [1, 0], "alice": [0, 1]}, counts


def unit_summarise_counts_identical_rows_separately():
    records = [
        ["assignee", "status"],
        ["alice", "open"],
        ["alice", "open"],
    ]
    counts, _ = ticket_summary.summarise(records)
    assert counts == {"alice": [2, 0]}, counts


def unit_summarise_rejects_an_empty_file():
    try:
        ticket_summary.summarise([])
    except ticket_summary.UsageError:
        pass
    else:
        raise AssertionError("expected a UsageError for an empty file")


# --- ordering and rendering (REQ-003, REQ-004) -------------------------------


def unit_ordered_assignees_uses_byte_order():
    counts = {"bob": [0, 0], "alice": [0, 0], "Zoe": [0, 0], "émile": [0, 0]}
    assert ticket_summary.ordered_assignees(counts) == [
        "Zoe",
        "alice",
        "bob",
        "émile",
    ]


def unit_render_prints_one_line_per_assignee_then_one_total():
    counts = {"bob": [1, 0], "alice": [3, 2]}
    assert ticket_summary.render(counts) == [
        "alice 3 2",
        "bob 1 0",
        "TOTAL 4 2",
    ]


def unit_render_of_an_empty_report_is_total_zero():
    assert ticket_summary.render({}) == ["TOTAL 0 0"]


# --- CSV reading (AMB-005) ---------------------------------------------------


def unit_read_records_honours_quoted_fields():
    path = os.path.join(SANDBOX, "quoted.csv")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write('assignee,status\n"Doe, John",open\n"O""Brien",closed\n')
    records = ticket_summary.read_records(path)
    assert records == [
        ["assignee", "status"],
        ["Doe, John", "open"],
        ['O"Brien', "closed"],
    ], records


def unit_read_records_reports_an_unreadable_path():
    try:
        ticket_summary.read_records(os.path.join(SANDBOX, "nope.csv"))
    except ticket_summary.UsageError as exc:
        assert "cannot read" in str(exc), str(exc)
    else:
        raise AssertionError("expected a UsageError for a missing file")


# --- Additional rule-level edge cases ---------------------------------------


def unit_resolve_columns_first_duplicate_name_wins():
    assert ticket_summary.resolve_columns(
        ["assignee", "status", "assignee", "status"]
    ) == (0, 1)


def unit_summarise_header_only_is_an_empty_report():
    counts, skipped = ticket_summary.summarise([["assignee", "status"]])
    assert counts == {}, counts
    assert skipped == 0, skipped


def unit_summarise_unknown_status_creates_no_assignee_entry():
    records = [
        ["assignee", "status"],
        ["bob", "pending"],
        ["bob", "in-progress"],
    ]
    counts, skipped = ticket_summary.summarise(records)
    assert counts == {}, counts
    assert skipped == 2, skipped


def unit_render_total_sums_every_assignee_column():
    counts = {"anna": [2, 1], "ben": [1, 3], "cy": [0, 0]}
    assert ticket_summary.render(counts) == [
        "anna 2 1",
        "ben 1 3",
        "cy 0 0",
        "TOTAL 3 4",
    ]


def unit_read_records_handles_crlf_line_endings():
    path = os.path.join(SANDBOX, "crlf.csv")
    with open(path, "wb") as handle:
        handle.write(b"assignee,status\r\nalice,open\r\nbob,closed\r\n")
    assert ticket_summary.read_records(path) == [
        ["assignee", "status"],
        ["alice", "open"],
        ["bob", "closed"],
    ]


TESTS = [
    ("unit_resolve_columns_reads_declared_positions", unit_resolve_columns_reads_declared_positions),
    (
        "unit_resolve_columns_trims_and_folds_header_names",
        unit_resolve_columns_trims_and_folds_header_names,
    ),
    ("unit_resolve_columns_ignores_extra_columns", unit_resolve_columns_ignores_extra_columns),
    ("unit_resolve_columns_names_each_missing_column", unit_resolve_columns_names_each_missing_column),
    (
        "unit_classify_status_recognises_open_and_closed_ignoring_case_and_blanks",
        unit_classify_status_recognises_open_and_closed_ignoring_case_and_blanks,
    ),
    ("unit_classify_status_rejects_every_other_value", unit_classify_status_rejects_every_other_value),
    (
        "unit_summarise_counts_open_and_closed_per_assignee",
        unit_summarise_counts_open_and_closed_per_assignee,
    ),
    ("unit_summarise_skips_every_unusable_shape", unit_summarise_skips_every_unusable_shape),
    (
        "unit_summarise_trims_the_assignee_into_the_group_key",
        unit_summarise_trims_the_assignee_into_the_group_key,
    ),
    ("unit_summarise_keeps_name_casing_apart", unit_summarise_keeps_name_casing_apart),
    ("unit_summarise_counts_identical_rows_separately", unit_summarise_counts_identical_rows_separately),
    ("unit_summarise_rejects_an_empty_file", unit_summarise_rejects_an_empty_file),
    ("unit_ordered_assignees_uses_byte_order", unit_ordered_assignees_uses_byte_order),
    (
        "unit_render_prints_one_line_per_assignee_then_one_total",
        unit_render_prints_one_line_per_assignee_then_one_total,
    ),
    ("unit_render_of_an_empty_report_is_total_zero", unit_render_of_an_empty_report_is_total_zero),
    ("unit_read_records_honours_quoted_fields", unit_read_records_honours_quoted_fields),
    ("unit_read_records_reports_an_unreadable_path", unit_read_records_reports_an_unreadable_path),
    ("unit_resolve_columns_first_duplicate_name_wins", unit_resolve_columns_first_duplicate_name_wins),
    ("unit_summarise_header_only_is_an_empty_report", unit_summarise_header_only_is_an_empty_report),
    (
        "unit_summarise_unknown_status_creates_no_assignee_entry",
        unit_summarise_unknown_status_creates_no_assignee_entry,
    ),
    ("unit_render_total_sums_every_assignee_column", unit_render_total_sums_every_assignee_column),
    ("unit_read_records_handles_crlf_line_endings", unit_read_records_handles_crlf_line_endings),
]


def write_report():
    directory = os.path.dirname(os.path.abspath(TAP_OUT))
    if directory:
        os.makedirs(directory, exist_ok=True)
    lines = ["1..%d" % len(RESULTS)]
    for index, (passed, name, diagnostic) in enumerate(RESULTS, 1):
        lines.append("%s %d - %s" % ("ok" if passed else "not ok", index, name))
        if not passed:
            for detail in str(diagnostic).splitlines() or [""]:
                lines.append("# %s" % detail)
    report = "\n".join(lines) + "\n"
    with open(TAP_OUT, "w", encoding="utf-8") as handle:
        handle.write(report)
    sys.stdout.write(report)


def main():
    for name, function in TESTS:
        check(name, function)
    write_report()
    return 0 if all(passed for passed, _, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
