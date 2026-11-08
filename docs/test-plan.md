# Test plan

Requirement: `docs/requirements/intake.yaml`. Entry point: `bash summary.sh <csv>`.
Test entry point: `bash run-tests.sh`. Mutation check: `bash mutation/run.sh`.

`bash run-tests.sh` runs three suites and exits nonzero when any check fails:

* `tests/test_summary.py` -- acceptance tests that drive the real
  `bash summary.sh` command in a subprocess against the checked-in fixtures in
  `tests/fixtures/`, written to `reports/tests.tap`;
* `tests/test_summary_units.py` -- unit tests that import `summary.py` and
  check the helper rules directly, written to `reports/tests-units.tap`;
* `tests/test_contract.py` -- delivery contract tests that read the TAP
  reports, check the mutation harness and assert the decision record, written
  to `reports/tests-contract.tap`.

## Acceptance criteria

| id | criterion | checks |
| --- | --- | --- |
| REQ-001 | `bash summary.sh <csv>` accepts the CSV as `$1`, exits 0 and writes the report to stdout | `test_entry_point_and_delivered_files_exist`, `test_relative_path_works_from_the_repository_root` |
| REQ-001 | `bash summary.sh sample/tickets.csv` works on a clean checkout | `test_documented_invocation_on_the_sample_file`, `test_sample_input_is_shipped` |
| REQ-001 | no network, service or interactive prompt is needed; the input is only read | `test_runs_without_interactive_input_or_network`, `test_tool_uses_no_network_client`, `test_input_file_is_not_modified`, `test_missing_argument_is_a_usage_error`, `test_nonexistent_input_is_an_error_with_empty_stdout` |
| REQ-002 | columns are located by header name, not position | `test_columns_are_located_by_header_name_not_position`, `test_resolve_columns_follows_names_not_positions` |
| REQ-002 | a quoted assignee containing a comma is one assignee | `test_quoted_assignee_with_a_comma_is_one_assignee` |
| REQ-002 | RFC 4180 quoting, embedded newlines, CRLF records | `test_quoted_fields_follow_rfc4180` |
| REQ-003 | `<assignee> <open> <closed>` counts per assignee | `test_mixed_per_assignee_open_and_closed_counts`, `test_three_open_one_closed_prints_the_required_line` |
| REQ-003 | an assignee with one status prints 0 in the other position | `test_assignee_with_only_one_status_prints_a_zero` |
| REQ-003 | every counted row contributes exactly once | `test_every_counted_row_contributes_exactly_once`, `test_summarise_records_counts_each_row_once` |
| REQ-004 | sorted by byte order; shuffling rows does not change the bytes | `test_assignees_are_sorted_by_byte_order`, `test_shuffling_data_rows_does_not_change_the_output` |
| REQ-004 | repeated runs are byte identical; output is locale independent | `test_repeated_runs_are_byte_identical`, `test_output_order_is_locale_independent` |
| REQ-005 | header-only file prints nothing and exits 0 | `test_header_only_file_prints_nothing_and_exits_zero` |
| REQ-005 | all-skipped file prints nothing and exits 0 | `test_all_rows_skipped_prints_nothing_and_exits_zero` |
| REQ-005 | no assignee absent from the data appears | `test_no_assignee_outside_the_data_is_reported`, `test_assignee_seen_only_in_skipped_rows_gets_no_line` |
| REQ-006 | `run-tests.sh` exits 0 and writes `reports/tests.tap` with no failing line | `test_run_tests_entry_point_runs_the_delivered_suites`, `test_acceptance_tap_report_is_readable_and_has_no_failures`, `test_default_acceptance_report_path_is_reports_tests_tap`; `reports/tests.tap` |
| REQ-006 | the suite fails when an expectation is broken | `test_a_broken_fixture_expectation_fails_with_a_tap_not_ok`; every mutant in `mutation/run.py` is killed by this suite |
| REQ-006 | each AMB-001..AMB-004 has a fixture that exercises it | see the AMB rows below |
| REQ-007 | `mutation/run.sh` writes `reports/mutation/mutation.json` | `test_mutation_entry_point_and_mutants_exist`, `test_mutation_report_path_matches_the_requirement`; `bash mutation/run.sh` |
| REQ-007 | the report has `total` > 0 and no survivors, and the harness fails on a survivor | `test_mutation_report_has_the_documented_shape`, `test_mutation_harness_fails_and_reports_a_surviving_mutant`; `bash mutation/run.sh` exit status |
| ADR-060 | every AMB answer is anchored in source and documented | `test_decisions_document_maps_every_ambiguity_to_source`, `test_every_ambiguity_has_a_greppable_source_comment` |
| AMB-001 | statuses trimmed, case-insensitive; other values skipped and counted | `test_status_is_trimmed_and_case_insensitive`, `test_unrecognised_status_is_skipped_and_counted_on_stderr`, `test_assignee_seen_only_in_skipped_rows_gets_no_line` |
| AMB-002 | one line per assignee with both counts, nothing else | `test_one_line_per_assignee_with_both_counts_and_nothing_else` |
| AMB-003 | bad rows skipped and counted on stderr; bad header is an error | `test_skipped_rows_are_counted_on_stderr_and_do_not_change_counts`, `test_empty_assignee_rows_are_skipped_and_counted`, `test_empty_status_rows_are_skipped_and_counted`, `test_short_rows_are_skipped_and_counted`, `test_header_without_required_columns_stops_the_run` |
| AMB-004 | assignee trimmed, case preserved | `test_assignee_is_trimmed_but_case_is_preserved` |
| REL-001 | the delivered tests fail when the counting behaviour is mutated | `mutation/run.py`: all mutants killed |

## Mutation coverage

The mutants edit `summary.py` (the counting logic run by `summary.sh`) and one
edits `summary.sh` itself: swap the per-assignee counts, reverse or drop the
sort, double the separator, stop trimming or folding statuses, treat an unknown
status as open, classify closed as open, count empty assignees, stop trimming or
start folding assignee names, skip rows without counting them, suppress or
always print the skip report, append a `TOTAL` line, read columns by position,
tolerate a bad header, treat an empty file as an empty report, count the header
row, overwrite instead of increment, and truncate the entry point's output.
Each mutant runs against a throwaway copy of the project with
`bash run-tests.sh`; a mutant the suite still passes is listed as a survivor
and makes the check exit nonzero.
