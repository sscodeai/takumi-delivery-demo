# Test plan -- `bash ticket-summary.sh`

Requirement: `docs/requirements/intake.yaml`. The delivered suite is run by
`bash run-tests.sh`, which writes `reports/tests.tap` (integration, drives the
real entry point) and `reports/tests-ticket-units.tap` (unit, imports
`ticket_summary.py`). Check names in the reports carry the id they defend.

| criterion | checks |
| --- | --- |
| REQ-001 entry point, stdout, errors | `req001_entry_point_exists_at_repo_root`, `req001_valid_csv_exits_zero_and_writes_only_the_report`, `req001_missing_file_exits_non_zero_with_stderr_diagnostic`, `req001_a_directory_instead_of_a_file_is_an_error`, `req001_no_argument_is_a_usage_error`, `req001_empty_file_is_a_usage_error` |
| REQ-002 header resolution | `req002_reversed_header_order_produces_the_same_report`, `req002_header_without_status_exits_non_zero_and_prints_nothing`, `req002_header_without_assignee_exits_non_zero_and_prints_nothing`, `req002_header_only_file_prints_total_zero`, `req002_extra_ignored_columns_and_mixed_case_header_names_are_allowed`, `unit_resolve_columns_*` |
| REQ-003 per-assignee lines, ordering, trimming | `req003_alice_prints_one_line_with_three_open_and_two_closed`, `req003_assignee_with_no_rows_in_one_status_still_prints_both_numbers`, `req003_lines_are_in_ascending_byte_order`, `req003_assignee_is_printed_trimmed`, `unit_ordered_assignees_uses_byte_order` |
| REQ-004 totals line | `req004_two_assignees_end_with_total_3_4`, `req004_total_equals_the_sums_of_the_printed_lines`, `req004_stdout_contains_only_assignee_lines_and_one_total`, `req004_empty_report_is_exactly_total_zero`, `unit_render_*` |
| REQ-005 recognised statuses | `req005_pending_rows_are_counted_in_neither_column`, `req005_open_and_closed_are_recognised_with_whitespace_and_case`, `amb001_unrecognised_status_makes_the_row_unusable`, `unit_classify_status_*` |
| REQ-006 unusable rows | `req006_malformed_row_leaves_the_stdout_report_unchanged`, `req006_skipped_diagnostic_is_on_stderr_and_never_on_stdout`, `req006_skipped_count_is_stated_for_a_clean_file_too`, `req006_short_row_and_whitespace_only_assignee_are_skipped`, `unit_summarise_skips_every_unusable_shape` |
| REQ-007 TAP suite | `bash run-tests.sh` itself; the integration checks above are the assertions in `reports/tests.tap` |
| REQ-008 mutation report | `bash mutation/run-mutation.sh`; `reports/mutation/mutation.json` has `total: 16` and no survivors |
| REQ-009 decisions in docs and tests | README section "Adopted readings"; AMB checks below |
| AMB-001 strict statuses | `amb001_unrecognised_status_makes_the_row_unusable`, `unit_classify_status_rejects_every_other_value` |
| AMB-002 skip-count | `req006_skipped_diagnostic_is_on_stderr_and_never_on_stdout`, `req006_skipped_count_is_stated_for_a_clean_file_too`, `unit_summarise_skips_every_unusable_shape` |
| AMB-003 case-sensitive grouping | `amb003_assignee_names_are_compared_case_sensitively`, `unit_summarise_keeps_name_casing_apart` |
| AMB-004 count-each-row | `amb004_identical_rows_count_as_two_tickets`, `unit_summarise_counts_identical_rows_separately` |
| AMB-005 quoted-aware CSV | `amb005_quoted_fields_keep_commas_and_doubled_quotes`, `amb005_quoted_status_field_is_read_as_one_field`, `unit_read_records_honours_quoted_fields` |

The mutation harness is the check that the suite is not merely green: every
mutant of the counting logic must make `bash run-tests.sh` exit non-zero, which
also produces a `not ok` line in the mutant's TAP report.
