# Test plan

Requirement: `docs/requirements/intake.yaml`. Entry point: `bash summary.sh <csv>`.

`bash run-tests.sh` runs `tests/test_summary.py` into `reports/tests.tap`; every
check below is executed on every run and the runner exits non-zero when any
fails. The inherited `passrate` suite is run as well, into
`reports/tests-passrate.tap`, and is not part of this requirement.

## Acceptance criteria

| id | criterion | checks |
| --- | --- | --- |
| REQ-001 | `bash summary.sh sample.csv` exits 0 and writes report lines to stdout | `req_001_declared_sample_report_is_exact`, `req_001_a_well_formed_run_writes_nothing_to_stderr` |
| REQ-001 | the script is at the repository root and reads the path from `$1` | `req_001_entry_point_sits_at_the_repository_root`, `req_001_reads_the_path_substituted_as_the_first_argument`, `req_001_a_relative_path_is_resolved_from_the_repository_root`, `req_001_no_argument_is_a_usage_error` |
| REQ-001 | the header row is never a data row, even with different case/whitespace | `req_001_header_row_is_never_a_data_row`, `req_001_header_only_file_is_exactly_one_line`, `req_004_the_header_is_not_counted_as_skipped`, `unit_looks_like_header_matches_case_and_blanks` |
| REQ-001 | stdout carries only report lines; diagnostics go to stderr | `req_001_stdout_carries_only_declared_shapes`, `req_001_a_missing_path_is_a_fatal_error_on_stderr`, `req_001_non_utf8_input_is_a_fatal_error_on_stderr`, `req_001_no_argument_is_a_usage_error` |
| REQ-001 | ordinary CSV shapes are read correctly | `req_001_a_quoted_region_containing_a_comma_stays_one_field`, `req_001_crlf_input_is_read_normally`, `req_001_a_utf8_bom_does_not_hide_the_header` |
| REQ-002 | `North,120.50` + `North,99.50` + `South,80.00` print the declared lines | `req_002_acceptance_example_is_exact` |
| REQ-002 | one line per distinct region; count integer, sum/mean two decimals | `req_002_one_line_per_distinct_region_and_no_absent_region`, `req_002_count_is_an_integer_and_numbers_have_two_decimals` |
| REQ-002 | fields are positional region, count, sum, mean | `req_002_fields_are_positional_region_count_sum_mean` |
| REQ-003 | exactly one `TOTAL` line, after all region lines | `req_003_exactly_one_totals_line_and_it_is_last_aggregate` |
| REQ-003 | the declared sample world totals `TOTAL 4 345.25` | `req_003_declared_sample_total_is_345_25` |
| REQ-003 | a header-only file prints `TOTAL 0 0.00` and exits 0 | `req_001_header_only_file_is_exactly_one_line`, `req_003_header_only_file_prints_total_zero` |
| REQ-006 | topics: 0.005-style halves, two-decimal shape, integer/one-decimal inputs | `req_006_positive_half_rounds_away_from_zero`, `req_006_negative_half_rounds_away_from_zero`, `req_006_integer_and_one_decimal_inputs_still_print_two_decimals` |
| REQ-004 | an `abc` amount is skipped; aggregates use only usable rows | `req_004_non_numeric_amount_is_skipped_and_excluded`, `req_004_skipped_rows_never_reach_any_aggregate` |
| REQ-004 | skipped count equals the number of unusable rows | `req_004_every_unusable_shape_is_skipped_once`, `req_004_skipped_count_equals_unusable_rows` |
| REQ-004 | a clean file has no `SKIPPED` line | `req_004_a_clean_file_prints_no_skipped_line` |
| REQ-005 | repeated regions merge into one line | `req_005_repeated_region_merges_into_one_line` |
| REQ-005 | region lines are in ascending byte order | `req_005_region_lines_are_sorted_by_utf8_bytes` |
| REQ-005 | differently spelled keys are not merged | `req_005_differently_spelled_keys_are_not_merged`, `req_005_internal_spacing_is_significant`, `unit_parse_region_keeps_the_key_verbatim` |
| REQ-006 | half away from zero at the second decimal place | `req_006_positive_half_rounds_away_from_zero`, `req_006_negative_half_rounds_away_from_zero`, `req_006_mean_negative_half_rounds_away_from_zero`, `unit_rounded_cents_rounds_halves_away_from_zero` |
| REQ-006 | mean from the unrounded sum; sum is rounded raw total | `req_006_mean_is_rounded_from_the_unrounded_sum`, `req_006_sum_is_the_rounded_total_of_raw_amounts` |
| REQ-006 | every printed number matches `-?[0-9]+\.[0-9]{2}`, no separators | `req_006_every_printed_number_matches_the_shape`, `req_006_below_half_rounds_down_and_never_prints_negative_zero`, `unit_format_cents_never_prints_negative_zero`, `unit_format_value_rounds_halves_away_from_zero` |
| REQ-007 | a shuffled file yields byte-identical stdout | `req_007_shuffled_rows_produce_identical_stdout`, `req_007_repeating_decimal_mean_is_order_independent` |
| AMB-001 | skip-count: unusable rows reported and excluded | `req_004_every_unusable_shape_is_skipped_once`, `req_004_skipped_count_equals_unusable_rows`, `req_004_skipped_rows_never_reach_any_aggregate` |
| AMB-002 | merge repeated region rows | `req_005_repeated_region_merges_into_one_line`, `rel_003_region_counts_and_sums_add_up_to_the_total` |
| AMB-003 | half-up rounding, also recomputed independently | `req_006_positive_half_rounds_away_from_zero`, `req_006_negative_half_rounds_away_from_zero`, `diff_001_random_two_decimal_files_match_an_independent_recomputation`, `diff_001_random_three_decimal_files_match_an_independent_recomputation` |
| AMB-004 | plain-decimal only; tolerant shapes are unusable | `req_004_plain_decimals_are_accepted`, `req_004_every_unusable_shape_is_skipped_once`, `unit_parse_amount_accepts_plain_decimals`, `unit_parse_amount_rejects_everything_else` |
| AMB-005 | exact region keys | `req_005_differently_spelled_keys_are_not_merged`, `req_005_internal_spacing_is_significant`, `unit_parse_region_keeps_the_key_verbatim` |
| AMB-001..005 | row-level parser and summary helpers | `unit_parse_row_accepts_usable_records`, `unit_parse_row_rejects_unusable_records`, `unit_summarise_emits_skipped_only_when_needed` |
| REL-003 | region counts and sums add up to the totals line | `rel_003_region_counts_and_sums_add_up_to_the_total` |
| REL-004 | row order invariance | `req_007_shuffled_rows_produce_identical_stdout` |
| DIFF-001 | independent recomputation matches every printed line | `diff_001_random_two_decimal_files_match_an_independent_recomputation`, `diff_001_random_three_decimal_files_match_an_independent_recomputation` |
