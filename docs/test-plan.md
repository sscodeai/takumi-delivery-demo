# Test plan and requirement coverage

Requirement document: `docs/requirements/intake.yaml`.
Delivered command under test: `bash summary.sh <csv>`.

## How to run

```
bash run-tests.sh
```

The root `run-tests.sh` is the discoverable entry point. It runs the unit
checks in `tests/test_units.py` and the integration checks in
`tests/test_summary.py` through one TAP report, writes that report to
`reports/tests.tap`, echoes it to stdout, and exits non-zero if any check fails.
The suite needs only `bash` and the Python 3 standard library; there is no
install or build step.

Both files are part of the same TAP run: the integration file imports the unit
list so a single report and a single exit status cover the whole suite.

## Acceptance criteria

| Requirement | Acceptance criterion | Checks |
| --- | --- | --- |
| REQ-001 | `summary.sh` runs with no install/build step, from any cwd and with spaces in the path | `req_001_entry_point_exists`, `req_001_entry_point_is_executable_with_shebang`, `req_001_runs_without_an_install_or_build_step`, `req_001_runs_from_another_working_directory`, `req_001_relative_input_path_resolves_from_cwd`, `req_001_input_path_may_contain_spaces` |
| REQ-001 | A readable file exits 0 and the report goes to stdout | `req_001_valid_csv_exits_zero`, `req_001_report_goes_to_stdout_not_stderr`, `req_001_process_terminates_on_its_own`, `req_001_stdin_is_not_consulted`, `unit_main_writes_the_report_to_stdout` |
| REQ-001 | A missing argument, missing file, directory or undecodable file is a non-zero stop with no report lines | `req_001_missing_argument_is_a_usage_error`, `req_001_extra_argument_is_rejected`, `req_001_missing_file_is_a_stop_error`, `req_001_directory_argument_is_a_stop_error`, `req_001_undecodable_input_is_a_stop_error`, `unit_main_rejects_a_wrong_argument_count`, `unit_main_stops_on_unreadable_input`, `unit_main_stops_on_a_permission_denied_input` |
| REQ-002 | `region,amount` and `Region , Amount` are accepted; the header is never a data row | `req_002_header_row_is_not_a_data_row`, `req_002_declared_header_is_accepted`, `req_002_header_is_trimmed_and_case_insensitive`, `req_002_quoted_header_is_read_normally`, `unit_locate_header_accepts_the_declared_header`, `unit_locate_header_trims_blanks_and_ignores_case` |
| REQ-002 | A missing or wrong header is fatal with no report lines | `req_002_a_missing_header_is_fatal`, `req_002_a_wrong_header_is_fatal`, `unit_locate_header_rejects_the_wrong_order`, `unit_locate_header_rejects_other_or_extra_columns`, `unit_locate_header_rejects_a_missing_header`, `unit_main_stops_on_a_missing_or_wrong_header` |
| REQ-002 | RFC 4180 quoting: a quoted comma region is one record | `req_002_a_quoted_comma_region_is_one_record`, `req_002_crlf_line_endings_are_accepted`, `req_002_utf8_bom_before_the_header_is_ignored`, `req_002_a_missing_final_newline_is_accepted` |
| REQ-003 | One line per distinct region, sorted by UTF-8 bytes | `req_003_sample_report`, `req_003_three_distinct_regions_yield_three_lines`, `req_003_exactly_one_line_per_region`, `req_003_regions_are_sorted_by_utf8_bytes`, `req_003_regions_are_case_sensitive`, `req_003_non_ascii_regions_survive` |
| REQ-003 | Region is trimmed before grouping/printing; case is significant | `req_003_regions_are_trimmed_before_grouping_and_printing`, `req_003_regions_are_case_sensitive`, `unit_parse_row_trims_the_region`, `unit_parse_row_keeps_region_case_and_inner_spaces` |
| REQ-003 | `<count> <sum> <mean>` are the group's row count, exact sum and mean | `req_003_count_is_the_number_of_accepted_rows_in_the_group`, `req_003_sum_and_mean_have_exactly_two_decimals`, `req_003_mean_is_sum_over_count`, `req_003_printed_aggregates_match_an_independent_recomputation`, `unit_summarise_groups_sorts_and_prints_the_sample` |
| REQ-004 | Exactly one `TOTAL <count> <sum>`, after the region lines, always printed | `req_004_there_is_exactly_one_total_line`, `req_004_total_line_shape_and_value`, `req_004_header_only_file_totals_zero`, `unit_summarise_reports_an_empty_report_for_a_header_only_file` |
| REQ-004 | Per-region counts and sums add up to TOTAL | `req_004_total_count_is_the_sum_of_region_counts`, `req_004_total_sum_is_the_sum_of_the_accepted_amounts`, `req_004_printed_region_sums_add_up_to_the_total_line`, `req_004_total_includes_every_duplicate_row` |
| REQ-005 | A malformed row is skipped, excluded and counted on `SKIPPED` (AMB-001) | `req_005_a_non_numeric_amount_is_counted_and_excluded`, `req_005_every_malformed_shape_is_counted`, `req_005_malformed_rows_do_not_change_any_aggregate`, `req_005_all_rows_malformed_still_exits_zero`, `unit_parse_row_skips_every_malformed_row`, `unit_summarise_counts_malformed_rows_without_aggregating_them`, `unit_read_records_turns_a_csv_error_into_a_malformed_record` |
| REQ-005 | `SKIPPED` appears once, after `TOTAL`, and is `0` for a clean file | `req_005_skipped_line_is_last_and_appears_once`, `req_005_clean_file_prints_skipped_zero` |
| REQ-006 | Identical rows each count as their own order (AMB-002) | `req_006_identical_rows_each_count`, `req_006_three_identical_rows_each_count`, `req_006_no_de_duplication`, `unit_summarise_keeps_every_duplicate_row` |
| REQ-007 | Exactly two decimals, half-up, exact arithmetic, reproducible | `req_007_mean_of_ten_thirds_is_three_point_three_three`, `req_007_two_point_zero_zero_five_rounds_up`, `req_007_trailing_zeros_are_always_printed`, `req_007_half_up_at_the_second_decimal`, `req_007_negative_halves_round_away_from_zero`, `req_007_repeated_runs_are_byte_identical`, `unit_format_money_rounds_an_exact_half_away_from_zero`, `unit_format_money_rounds_negative_halves_away_from_zero`, `unit_format_money_truncates_below_a_half`, `unit_format_money_always_prints_two_decimals` |
| REQ-008 | Zero and negative amounts are valid; region case matters | `req_008_zero_and_negative_amounts_are_included`, `req_008_zero_amount_counts`, `req_008_region_case_is_significant` |
| REQ-009 | Shuffling rows leaves the report byte-identical | `req_009_shuffled_rows_give_the_same_report`, `req_009_permutations_with_duplicates_and_bad_rows`, `req_009_all_permutations_of_a_small_fixture_are_identical` |
| REQ-010 | One documented command runs the delivered suite | `req_010_run_tests_entry_point_exists`, and `bash run-tests.sh` itself |

## Ambiguity decisions

| Ambiguity | Chosen behaviour | Checks |
| --- | --- | --- |
| AMB-001 | `skip-count`: skip the malformed row, exclude it, count it on `SKIPPED` | `req_005_*`, `unit_parse_row_skips_every_malformed_row`, `unit_summarise_counts_malformed_rows_without_aggregating_them`, `unit_read_records_turns_a_csv_error_into_a_malformed_record` |
| AMB-002 | `merge`: identical rows each count as their own order | `req_006_*`, `unit_summarise_keeps_every_duplicate_row` |
| AMB-003 | `half-up`: an exact half rounds away from zero at two decimals | `req_007_half_up_at_the_second_decimal`, `req_007_two_point_zero_zero_five_rounds_up`, `req_007_negative_halves_round_away_from_zero`, `unit_format_money_rounds_an_exact_half_away_from_zero`, `unit_format_money_rounds_negative_halves_away_from_zero` |

## Relation coverage

* `REL-001` (malformed-row-accounting, AMB-001) is checked by comparing a dirty
  fixture with its clean twin: the aggregates match and only `SKIPPED` grows.
* `REL-002` (duplicate-resolution, AMB-002) is checked by repeating identical
  rows and asserting count and sum both grow.
* `REL-003` (additivity) is checked by summing the printed per-region counts and
  amounts against the printed `TOTAL` line.
* `REL-004` (row-order invariance) is checked by running the same multiset of
  rows in different orders and comparing stdout byte-for-byte.
* `DIFF-001` (independent aggregation, AMB-003) is checked by recomputing money
  with `decimal.Decimal` in `req_004_total_sum_is_the_sum_of_the_accepted_amounts`,
  by recomputing every region's count/sum/mean independently in
  `req_003_printed_aggregates_match_an_independent_recomputation`, and by direct
  half-up boundary cases in the `req_007_*` and `unit_format_money_*` checks.
