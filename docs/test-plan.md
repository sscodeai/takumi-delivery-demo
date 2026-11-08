# Test plan

Requirement: `docs/requirements/intake.yaml`. Entry point: `bash summary.sh <csv>`.
Test entry point: `bash run-tests.sh`. Mutation check: `bash tests/mutation.sh`.

`bash run-tests.sh` runs two suites for this delivery and exits non-zero when
any check fails:

* `tests/test_summary.py` -- acceptance tests that drive the real
  `bash summary.sh` command in a subprocess against the checked-in fixtures in
  `tests/fixtures/`, written to `reports/tests.tap`;
* `tests/test_summary_units.py` -- unit tests that import `summary.py` and
  check the helper rules directly, written to
  `reports/tests-summary-units.tap`.

## Acceptance criteria

| id | criterion | checks |
| --- | --- | --- |
| REQ-001 | `bash summary.sh <csv>` accepts the CSV as `$1`, exits 0 and writes the report to stdout | `test_entry_point_sits_at_the_repository_root`, `test_first_argument_is_the_csv_path_and_exit_is_zero`, `test_relative_path_works_from_the_repository_root` |
| REQ-001 | no other argument is required and the input is not modified | `test_input_file_is_not_modified`, `test_missing_argument_is_a_usage_error`, `test_nonexistent_input_is_an_error_with_empty_stdout` |
| REQ-002 | the header line is recognised and excluded from every count | `test_header_line_is_recognised_and_not_counted`, `test_header_only_file_reports_zero_totals`, `test_read_rows_accepts_a_utf8_bom_header` |
| REQ-002 | each accepted row increments exactly one assignee/status cell | `test_every_accepted_row_is_counted_exactly_once`, `test_mixed_per_assignee_open_and_closed_counts` |
| REQ-003 | every distinct assignee appears exactly once | `test_each_assignee_appears_on_exactly_one_line` |
| REQ-003 | an assignee with both statuses shows both counts | `test_mixed_per_assignee_open_and_closed_counts`, `test_format_report_prints_exactly_one_total_line` |
| REQ-003 | an assignee with one status is still reported, other count zero | `test_assignee_with_one_status_still_prints_both_counts`, `test_summarise_keeps_a_zero_slot_for_a_single_status_assignee` |
| REQ-003 | per-assignee open and closed sums equal the accepted rows | `test_totals_equal_the_sum_of_per_assignee_counts`, `test_format_report_totals_are_the_sums_of_the_lines` |
| REQ-004 | exactly one totals line, printed last | `test_exactly_one_totals_line`, `test_format_report_prints_exactly_one_total_line` |
| REQ-004 | totals equal the per-assignee sums and cover every accepted row | `test_totals_equal_the_sum_of_per_assignee_counts`, `test_totals_are_correct_on_the_zero_count_fixture`, `test_every_accepted_row_is_counted_exactly_once` |
| REQ-005 | `run-tests.sh` exits 0 on a correct implementation and writes TAP | this document's suites; `reports/tests.tap` |
| REQ-005 | `not ok` for wrong counts, swapped buckets or a missing totals line | demonstrated by every mutant in `tests/mutation.sh` |
| REQ-006 | `tests/mutation.sh` writes `reports/mutation/mutation.json` | `tests/mutation_runner.py` (15 mutants, `total` > 0) |
| AMB-001 | one line per assignee carrying both counts | `test_mixed_per_assignee_open_and_closed_counts`, `test_format_report_prints_exactly_one_total_line` |
| AMB-002 | sorted by locale-independent byte order | `test_assignees_are_sorted_by_locale_independent_bytes`, `test_report_order_does_not_depend_on_row_order`, `test_format_report_sorts_by_utf8_bytes` |
| AMB-003 | only exact lowercase `open` / `closed` recognised | `test_only_exact_lowercase_status_tokens_are_recognised`, `test_summarise_skips_unrecognised_statuses` |
| AMB-004 | empty assignee / unrecognised status / short row skipped silently | `test_unusable_rows_are_skipped_without_affecting_counts`, `test_summarise_skips_an_empty_assignee`, `test_read_rows_skips_a_row_that_is_too_short` |
| AMB-005 | missing category printed as `0` | `test_assignee_with_one_status_still_prints_both_counts`, `test_summarise_keeps_a_zero_slot_for_a_single_status_assignee` |
| REL-001 | the delivered tests fail when the counting behaviour is mutated | `tests/mutation_runner.py`: all 15 mutants killed |

## Mutation coverage

The mutants edit `summary.py` (the counting logic run by `summary.sh`) and one
edits `summary.sh` itself:
swap per-assignee counts, swap totals, drop the totals line, move the totals
line first, count the header, omit all-open assignees, treat an unrecognised
status as open, count empty assignees, keep too-short rows, reverse the sort,
accept case-insensitive statuses, derive either total from the assignee count,
double-count every row, and make the entry point filter out the totals line.
Each is run against a copy of the project with
`bash run-tests.sh`; a mutant that the suite still passes is listed as a
survivor and makes the check exit non-zero.
