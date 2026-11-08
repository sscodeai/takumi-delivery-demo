# Test plan

Requirement: `docs/requirements/intake.yaml`. Entry point: `bash summary.sh <csv>`.
Test entry point: `bash run-tests.sh` (scenario SCN-001). Mutation check:
`bash mutation/run.sh`.

`bash run-tests.sh` runs three suites and exits nonzero when any check fails:

* `tests/test_summary.py` -- acceptance tests that drive the real
  `bash summary.sh` command in subprocesses against the declared sample and
  the checked-in fixtures in `tests/fixtures/`, written to
  `reports/tests.tap`;
* `tests/test_summary_units.py` -- unit tests that import `summary.py` and
  check the helper rules directly, written to `reports/tests-units.tap`;
* `tests/test_contract.py` -- delivery contract tests that read the TAP
  reports, prove a wrong aggregate fails the suite, check the mutation harness
  and assert the decision record, written to `reports/tests-contract.tap`.

## Acceptance criteria

| id | criterion | checks |
| --- | --- | --- |
| REQ-001 | `bash summary.sh <csv>` accepts the CSV as `$1`, exits 0 and writes the report to stdout | `test_declared_sample_without_a_header_produces_the_required_report`, `test_shipped_sample_file_is_the_declared_sample` |
| REQ-001 | no argument or an unreadable path exits nonzero with a stderr diagnostic and empty stdout | `test_missing_argument_is_a_usage_error`, `test_unreadable_path_is_an_error_with_no_partial_report` |
| REQ-001 | no network, no interactive input, input only read | `test_tool_uses_no_network_client`, `test_input_file_is_not_modified` |
| REQ-001 | a header without both named columns is an error with empty stdout | `test_header_without_the_amount_column_stops_the_run`, `test_header_without_the_region_column_stops_the_run` |
| REQ-002 | columns are located by header name, not position | `test_columns_are_located_by_header_name_not_position`, `test_resolve_columns_follows_names_not_positions` |
| REQ-002 | extra columns do not change the numbers | `test_extra_columns_do_not_change_the_numbers`, `test_resolve_columns_ignores_extra_columns` |
| REQ-002 | the declared headerless sample is accepted with `region,amount` order | `test_declared_sample_without_a_header_produces_the_required_report`, `test_sample_with_a_header_produces_the_same_report`, `test_looks_like_header_rejects_a_data_row` |
| REQ-002 | blank lines are neither records nor skipped rows | `test_blank_lines_are_neither_records_nor_skipped_rows`, `test_is_blank_record_treats_empty_and_whitespace_lines_as_blank` |
| REQ-003 | one line per region: `<region> <count> <sum> <mean>` | `test_per_region_count_sum_and_mean_are_printed`, `test_region_line_has_exactly_four_fields_in_the_declared_shape`, `test_format_report_renders_sorted_region_lines_then_total_then_skipped` |
| REQ-003 | region lines sorted, unique, one per distinct region | `test_region_lines_are_sorted_lexicographically_and_unique`, `test_region_line_count_equals_distinct_regions` |
| REQ-003 | the declared sample prints `North 2 220.00 110.00` | `test_declared_sample_without_a_header_produces_the_required_report` |
| REQ-004 | exactly one `TOTAL <count> <sum>` after the region lines, no mean | `test_total_line_is_printed_exactly_once_after_the_region_lines`, `test_total_line_carries_only_count_and_sum`, `test_format_report_has_no_overall_mean_on_the_total_line` |
| REQ-004 | TOTAL count and sum are additive over the region lines | `test_total_count_and_sum_are_additive_over_the_region_lines` |
| REQ-004 | the declared sample prints `TOTAL 4 345.25` | `test_declared_sample_without_a_header_produces_the_required_report` |
| REQ-005 | `SKIPPED <n>` is always the last line, exactly once, `0` for a clean file | `test_skipped_line_is_always_last_and_zero_for_a_clean_file`, `test_format_report_always_prints_the_skipped_count_last` |
| REQ-005 | malformed rows are counted and excluded from every aggregate | `test_malformed_rows_are_skipped_counted_and_excluded_from_totals`, `test_two_malformed_rows_are_counted_as_two`, `test_summarise_records_skips_and_counts_malformed_rows` |
| REQ-006 | means and sums have exactly two decimals, counts are integers | `test_whole_number_mean_is_printed_with_two_decimals`, `test_zero_amount_is_formatted_as_two_decimals`, `test_format_amount_prints_exactly_two_decimals` |
| REQ-006 | mean `86.3125` prints `86.31` | `test_mean_with_more_than_two_decimals_rounds_half_up` |
| REQ-007 | repeated region+amount rows merge (AMB-002) | `test_identical_rows_are_merged_into_the_aggregates`, `test_summarise_records_merges_identical_rows` |
| REQ-008 | shuffling data rows yields byte-identical stdout | `test_shuffling_data_rows_does_not_change_stdout_bytes`, `test_repeated_runs_are_byte_identical` |
| REQ-009 | header-only file prints `TOTAL 0 0.00` then `SKIPPED 0`, exit 0 | `test_header_only_file_prints_only_total_and_skipped`, `test_header_only_file_with_blank_lines_is_an_empty_report`, `test_empty_file_is_a_valid_empty_report`, `test_blank_only_file_is_a_valid_empty_report`, `test_format_report_is_empty_apart_from_total_and_skipped` |
| REQ-010 | a negative amount is included as a refund (AMB-004) | `test_negative_amount_is_included_as_a_refund`, `test_parse_amount_accepts_negative_refunds`, `test_format_amount_rounds_negative_halves_away_from_zero` |
| REQ-011 | `run-tests.sh` exits 0 and writes readable TAP to `reports/tests.tap` | `test_run_tests_entry_point_runs_the_delivered_suites`, `test_acceptance_tap_report_is_readable_and_has_no_failures`, `test_default_acceptance_report_path_is_reports_tests_tap`; `reports/tests.tap` |
| REQ-011 | the report asserts per-region totals, averages, TOTAL, SKIPPED and rounding | `test_acceptance_report_has_ok_lines_for_each_required_behaviour`; the named checks above |
| REQ-011 | a deliberately wrong aggregate makes a delivered test fail | `test_a_wrong_aggregate_makes_the_delivered_suite_fail` (mean replaced by sum in a throwaway copy); every mutant in `mutation/run.py` is killed |
| REQ-011 | `mutation/run.sh` writes `reports/mutation/mutation.json` with no survivors | `test_mutation_entry_point_and_mutants_exist`, `test_mutation_report_path_matches_the_documented_shape`, `test_mutation_harness_fails_and_reports_a_surviving_mutant`; `bash mutation/run.sh` |
| ADR-060 | every AMB answer is anchored in source and documented | `test_decisions_document_maps_every_ambiguity_to_source`, `test_every_ambiguity_has_a_greppable_source_comment` |

## Ambiguities

| id | answer | checks |
| --- | --- | --- |
| AMB-001 | `skip-count`: unusable rows are skipped, excluded and counted on `SKIPPED` | `test_malformed_rows_are_skipped_counted_and_excluded_from_totals`, `test_two_malformed_rows_are_counted_as_two`, `test_short_row_is_skipped_and_counted`, `test_empty_region_is_skipped_and_counted`, `test_parse_amount_rejects_unusable_values` |
| AMB-002 | `merge`: a repeated region+amount is a separate order, counted and added | `test_identical_rows_are_merged_into_the_aggregates`, `test_summarise_records_merges_identical_rows` |
| AMB-003 | `half-up`: means round half away from zero to two decimals | `test_mean_with_more_than_two_decimals_rounds_half_up`, `test_mean_at_an_exact_half_rounds_away_from_zero`, `test_format_amount_rounds_half_up` |
| AMB-004 | `include`: a well-formed negative amount is a normal record | `test_negative_amount_is_included_as_a_refund`, `test_parse_amount_accepts_negative_refunds` |
