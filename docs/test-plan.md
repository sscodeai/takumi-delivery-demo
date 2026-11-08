# Test plan

Requirement: `docs/requirements/intake.yaml`. Entry point: `bash summary.sh <csv>`.

`bash run-tests.sh` runs two suites for this delivery and exits non-zero when
any check fails:

* `tests/test_summary.py` -- integration tests that drive the real entry point
  in a subprocess, written to `reports/tests.tap`;
* `tests/test_summary_units.py` -- unit tests that import `summary.py` and
  check the helper rules directly, written to
  `reports/tests-summary-units.tap`.

The inherited `passrate` suite is run as well, into
`reports/tests-passrate.tap`, and is not part of this requirement.

## Acceptance criteria

| id | criterion | checks |
| --- | --- | --- |
| REQ-001 | `bash summary.sh <csv>` exits 0 and writes the report to stdout | `req_001_declared_sample_report_is_exact`, `req_001_a_well_formed_run_writes_nothing_to_stderr` |
| REQ-001 | the script is at the repository root and reads the path from `$1` | `req_001_entry_point_sits_at_the_repository_root`, `req_001_reads_the_csv_named_by_the_first_argument`, `req_001_relative_path_works_from_the_repository_root`, `req_001_missing_argument_is_a_usage_error`, `req_001_extra_argument_is_rejected` |
| REQ-001 | a few thousand rows finish well inside 120000 ms | `req_001_a_few_thousand_rows_finish_well_inside_the_bound` |
| REQ-002 | swapped header order produces the same report | `req_002_swapped_header_columns_produce_the_same_report`, `req_011_header_order_does_not_change_the_report` |
| REQ-002 | a header lacking `region` or `amount` is fatal and prints no report | `req_002_missing_region_header_is_fatal`, `req_002_missing_amount_header_is_fatal` |
| REQ-002 | columns are mapped by name, including extra columns | `req_002_extra_header_columns_are_followed_by_name`, `req_002_header_names_tolerate_blank_and_case_variation` |
| REQ-003 | one line per present region, no absent region | `req_003_one_line_per_present_region_and_no_absent_region`, `req_006_repeated_region_is_one_line` |
| REQ-003 | second field is the region sum | `req_003_revenue_is_the_region_sum` |
| REQ-003 | third field is the region sum divided by its count | `req_003_average_divides_the_region_sum_by_its_count`, `req_007_average_rounds_from_the_unrounded_sum` |
| REQ-004 | totals revenue equals the sum of printed region revenues | `req_004_totals_revenue_equals_the_sum_of_printed_region_revenues`, `rel_002_region_revenues_and_counts_add_up_to_the_total` |
| REQ-004 | totals order count equals counted rows / region counts | `req_004_order_count_equals_counted_rows` |
| REQ-004 | exactly one `TOTAL` line, after the region and `SKIPPED` lines | `req_004_exactly_one_totals_line`, `req_004_totals_line_is_printed_after_skipped` |
| REQ-005 | 3 valid + 2 malformed rows print `SKIPPED 2` and use only valid rows | `req_005_three_valid_two_malformed_rows_are_aggregated_and_counted` |
| REQ-005 | all-malformed input exits 0 with `SKIPPED <n>` and `TOTAL 0.00 0` | `req_005_all_malformed_rows_exit_zero` |
| REQ-005 | `SKIPPED 0` for a clean file | `req_005_clean_file_prints_skipped_zero` |
| REQ-005 | each malformed shape is skipped once | `req_005_wrong_field_count_rows_are_malformed`, `req_005_blank_region_rows_are_malformed`, `req_005_non_numeric_amounts_are_malformed` |
| REQ-005 | plain decimal amounts are accepted | `req_005_plain_decimal_shapes_are_accepted` |
| REQ-006 | a duplicated row raises revenue, region count and total count | `req_006_duplicate_row_counts_twice` |
| REQ-006 | a region is never printed twice | `req_006_repeated_region_is_one_line` |
| REQ-007 | `0.125` prints `0.13` | `req_007_single_amount_0_125_rounds_up` |
| REQ-007 | `2.674` prints `2.67` | `req_007_single_amount_2_674_rounds_down` |
| REQ-007 | every printed number matches `^-?[0-9]+\.[0-9]{2}$` | `req_007_every_printed_number_matches_the_shape`, `req_007_integer_and_one_decimal_amounts_print_two_decimals` |
| REQ-007 | negative halves round away from zero; no negative zero | `req_007_negative_half_rounds_away_from_zero`, `req_007_negative_average_half_rounds_away_from_zero`, `req_007_no_negative_zero_is_printed` |
| REQ-008 | `north` and `North` are two regions | `req_008_case_differs_means_two_regions` |
| REQ-008 | ` north ` aggregates and prints as `north` | `req_008_surrounding_whitespace_is_trimmed_and_merged`, `req_008_printed_id_is_the_trimmed_first_seen_text` |
| REQ-008 | internal spacing is significant | `req_008_internal_spacing_is_significant` |
| REQ-009 | negative and zero amounts are valid measures | `req_009_negative_and_zero_amounts_are_valid`, `req_009_zero_amount_is_valid`, `req_009_a_negative_total_prints_a_leading_minus` |
| REQ-009 | negative amounts are never counted as skipped | `req_009_negative_amounts_never_appear_in_skipped` |
| REQ-010 | a header-only file prints exactly `SKIPPED 0` and `TOTAL 0.00 0` | `req_010_header_only_file_prints_only_skipped_and_total`, `req_010_header_only_file_prints_no_region_line` |
| REQ-011 | region lines are in ascending byte order | `req_011_region_lines_are_sorted_by_bytes` |
| REQ-011 | shuffling rows leaves stdout byte-identical | `req_011_shuffled_rows_produce_identical_stdout` |
| REQ-012 | a missing path, empty file, directory or non-UTF-8 file is fatal on stderr with empty stdout | `req_012_nonexistent_path_is_fatal_and_silent_on_stdout`, `req_012_empty_file_is_fatal`, `req_012_directory_path_is_fatal`, `req_012_non_utf8_input_is_fatal` |
| AMB-001 | skip-count: malformed rows excluded and reported | `req_005_three_valid_two_malformed_rows_are_aggregated_and_counted`, `req_005_all_malformed_rows_exit_zero`, `req_005_non_numeric_amounts_are_malformed` |
| AMB-002 | merge: every occurrence counts | `req_006_duplicate_row_counts_twice`, `rel_002_region_revenues_and_counts_add_up_to_the_total` |
| AMB-003 | half-up at two decimals, also recomputed independently | `req_007_single_amount_0_125_rounds_up`, `req_007_negative_half_rounds_away_from_zero`, `diff_001_random_two_decimal_file_matches_recomputation`, `diff_001_random_three_decimal_file_matches_recomputation` |
| AMB-004 | exact-trimmed region keys | `req_008_case_differs_means_two_regions`, `req_008_surrounding_whitespace_is_trimmed_and_merged`, `req_008_internal_spacing_is_significant` |
| REL-002 | additivity of region revenues and counts | `rel_002_region_revenues_and_counts_add_up_to_the_total`, `req_004_totals_revenue_equals_the_sum_of_printed_region_revenues` |
| REL-004 | row-order invariance | `req_011_shuffled_rows_produce_identical_stdout` |
| DIFF-001 | independent recomputation matches every printed line | `diff_001_random_two_decimal_file_matches_recomputation`, `diff_001_random_three_decimal_file_matches_recomputation` |
| CSV | ordinary CSV shapes are read correctly | `csv_quoted_region_with_comma_is_one_field`, `csv_crlf_input_is_read_normally`, `csv_utf8_bom_does_not_hide_the_header` |
| REQ-005 | a blank physical line has a wrong field count and is counted | `req_005_a_blank_physical_line_is_a_wrong_field_count_row` |

## Unit coverage

These checks import `summary.py` directly. They cover the same criteria from
the inside, including values that are awkward to express through a CSV file.

| id | unit checks |
| --- | --- |
| REQ-001 | `unit_main_requires_exactly_one_argument`, `unit_main_valid_file_returns_zero_and_the_report` |
| REQ-002 | `unit_header_columns_resolves_the_declared_order`, `unit_header_columns_resolves_swapped_columns`, `unit_header_columns_ignores_extra_columns`, `unit_header_columns_trims_and_folds_names`, `unit_header_columns_uses_the_first_matching_column`, `unit_header_columns_missing_region_is_fatal`, `unit_header_columns_missing_amount_is_fatal`, `unit_header_columns_missing_both_names_both`, `unit_header_columns_rejects_an_unparsable_header` |
| REQ-003 | `unit_summarise_declared_sample_is_exact`, `unit_summarise_average_uses_the_unrounded_sum` |
| REQ-004 | `unit_summarise_total_revenue_is_the_sum_of_printed_region_revenues`, `unit_summarise_total_orders_is_the_sum_of_region_counts`, `unit_summarise_prints_exactly_one_skipped_and_one_total_line` |
| REQ-005 | `unit_parse_amount_rejects_unreadable_cells`, `unit_read_records_turns_an_unparsable_record_into_the_malformed_sentinel`, `unit_summarise_three_valid_two_malformed`, `unit_summarise_all_malformed_counts_each_row_once`, `unit_summarise_wrong_field_count_is_malformed`, `unit_summarise_blank_region_is_malformed`, `unit_summarise_non_decimal_amount_is_malformed` |
| REQ-006 | `unit_summarise_merges_every_duplicate_occurrence` |
| REQ-007 | `unit_round_cents_rounds_an_exact_half_away_from_zero`, `unit_round_cents_rounds_non_halves_by_nearest`, `unit_round_cents_has_no_negative_zero`, `unit_format_cents_prints_exactly_two_decimals`, `unit_format_value_composes_rounding_and_formatting`, `unit_format_value_always_matches_the_declared_shape`, `unit_summarise_never_prints_negative_zero` |
| REQ-008 | `unit_parse_region_trims_every_ascii_whitespace_character`, `unit_parse_region_keeps_internal_spacing`, `unit_parse_region_is_case_sensitive`, `unit_parse_region_returns_none_for_blank_cells`, `unit_parse_region_does_not_trim_non_ascii_whitespace`, `unit_summarise_region_key_is_trimmed_and_case_sensitive` |
| REQ-009 | `unit_parse_amount_keeps_negative_and_zero_as_valid_measures`, `unit_summarise_negative_values_stay_valid_and_format_with_a_sign`, `unit_summarise_zero_amounts_are_valid_orders` |
| REQ-010 | `unit_summarise_header_only_is_an_empty_report` |
| REQ-011 | `unit_summarise_sorts_region_lines_by_utf8_bytes` |
| REQ-012 | `unit_main_missing_path_is_fatal_with_empty_stdout`, `unit_main_empty_file_is_fatal_with_empty_stdout`, `unit_summarise_rejects_an_empty_file` |
| AMB-001 | `unit_summarise_three_valid_two_malformed`, `unit_summarise_all_malformed_counts_each_row_once`, `unit_summarise_wrong_field_count_is_malformed`, `unit_summarise_blank_region_is_malformed`, `unit_summarise_non_decimal_amount_is_malformed`, `unit_read_records_turns_an_unparsable_record_into_the_malformed_sentinel` |
| AMB-002 | `unit_summarise_merges_every_duplicate_occurrence` |
| AMB-003 | `unit_parse_amount_accepts_plain_decimals_exactly`, `unit_parse_amount_never_uses_binary_floats`, `unit_round_cents_rounds_an_exact_half_away_from_zero`, `unit_round_cents_rounds_non_halves_by_nearest`, `unit_format_value_composes_rounding_and_formatting`, `unit_format_value_always_matches_the_declared_shape` |
| AMB-004 | `unit_parse_region_trims_every_ascii_whitespace_character`, `unit_parse_region_is_case_sensitive`, `unit_parse_region_keeps_internal_spacing`, `unit_parse_region_returns_none_for_blank_cells`, `unit_summarise_region_key_is_trimmed_and_case_sensitive` |
