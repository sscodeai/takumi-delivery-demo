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
| REQ-001 | `summary.sh` exists at the root and runs with no install/build step | `req_001_entry_point_exists`, `req_001_entry_point_is_executable_with_shebang`, `req_001_runs_without_an_install_or_build_step`, `req_001_runs_from_another_working_directory`, `req_001_relative_input_path_resolves_from_cwd`, `req_001_input_path_may_contain_spaces` |
| REQ-001 | A well-formed CSV exits 0 and writes the report to stdout | `req_001_valid_csv_exits_zero`, `req_001_report_goes_to_stdout_not_stderr`, `req_001_process_terminates_on_its_own`, `req_001_stdin_is_not_consulted`, `unit_main_writes_the_report_to_stdout` |
| REQ-002 | The header row never becomes a data row or a suite line | `req_002_header_row_is_not_a_data_row`, `req_002_a_data_row_is_not_mistaken_for_a_header`, `req_002_header_only_file_reports_an_empty_total`, `unit_locate_columns_treats_a_data_row_as_data` |
| REQ-002 | `suite,passed,total` and `total,suite,passed` give the same report | `req_002_declared_column_order_is_the_report`, `req_002_reordered_columns_yield_the_same_report`, `req_002_reordered_header_still_merges_a_repeated_suite`, `req_002_extra_columns_anywhere_do_not_disturb_the_lookup`, `unit_locate_columns_follows_a_reordered_header` |
| REQ-003 | Three distinct suites yield exactly three suite lines | `req_003_three_distinct_suites_yield_three_lines`, `req_003_the_report_has_no_other_lines`, `req_003_each_suite_line_carries_four_fields`, `req_003_suite_lines_are_emitted_before_the_total` |
| REQ-003 | A repeated suite yields exactly one line for it | `req_003_a_repeated_suite_yields_one_line`, `amb_002_merge_still_prints_one_line`, `unit_summarise_merges_a_repeated_suite` |
| REQ-003 | Suite values are echoed verbatim (no case folding or trimming) | `req_003_suite_names_are_not_case_folded`, `req_003_suite_names_are_echoed_verbatim`, `req_003_suite_ids_are_not_trimmed`, `req_003_non_ascii_suite_names_survive`, `req_003_a_quoted_comma_stays_one_suite_line`, `unit_parse_row_does_not_trim_the_suite_id` |
| REQ-003 | Order is first appearance in the input | `req_003_suites_are_in_first_appearance_order`, `amb_002_merge_keeps_first_appearance_order`, `unit_summarise_keeps_first_appearance_order` |
| REQ-004 | `48/50` prints `96.0`, `12/12` prints `100.0`, `1/3` prints `33.3` | `req_004_declared_examples`, `amb_001_exact_half_rounds_up`, `unit_percentage_uses_points_and_half_up` |
| REQ-004 | The percentage token always has exactly one decimal digit | `req_004_percentage_always_has_exactly_one_decimal`, `req_004_percentage_grid_matches_half_up`, `unit_render_tenths_always_prints_one_decimal` |
| REQ-004 | The value is a percentage point value, not a 0-1 fraction | `req_004_percentage_is_in_points_not_a_fraction`, `unit_percentage_uses_points_and_half_up` |
| REQ-004 | Zero, full, thirds, large and decimal counts follow the same rule | `req_004_zero_percent_is_zero_point_zero`, `req_004_a_full_pass_is_one_hundred`, `req_004_thirds_round_to_one_decimal`, `req_004_large_counts_keep_the_exact_ratio`, `req_004_decimal_counts_are_exact` |
| REQ-005 | Exactly one line starts with `TOTAL` and it is last | `req_005_there_is_exactly_one_total_line`, `req_005_total_is_the_last_line`, `req_003_the_report_has_no_other_lines` |
| REQ-005 | `TOTAL` equals the sum of printed denominators | `req_005_total_is_the_sum_of_printed_denominators`, `req_005_single_suite_total`, `req_005_header_only_file_total_is_zero`, `req_005_total_sums_every_occurrence_of_a_merged_suite`, `req_005_total_sums_denominators_across_suites`, `req_005_total_keeps_decimal_denominators`, `req_004_percentage_grid_matches_half_up`, `unit_summarise_totals_decimal_denominators` |
| REQ-006 | Repeated suites merge by summing passed and total (AMB-002) | `amb_002_merge_sums_passed_and_total`, `amb_002_merge_percentage_uses_the_summed_counts`, `amb_002_merge_is_not_the_last_row`, `amb_002_merge_is_not_the_first_row`, `amb_002_merge_over_three_occurrences`, `unit_summarise_merges_a_repeated_suite` |
| REQ-006 | An unusable row neither aborts the run nor prints a suite line (AMB-003) | `amb_003_non_numeric_passed_row_is_skipped`, `amb_003_non_numeric_total_row_is_skipped`, `amb_003_empty_count_cells_are_skipped`, `amb_003_quoted_non_numeric_counts_are_skipped`, `amb_003_zero_total_row_is_skipped`, `amb_003_zero_total_written_as_a_decimal_is_skipped`, `amb_003_short_row_is_skipped`, `amb_003_blank_line_is_skipped`, `amb_003_blank_suite_id_is_skipped`, `amb_003_negative_counts_are_skipped`, `amb_003_skipped_rows_do_not_change_any_aggregate`, `amb_003_a_suite_with_only_bad_rows_is_absent`, `amb_003_all_rows_bad_still_exits_zero_with_total_zero`, `amb_003_no_skipped_counter_is_printed`, `unit_parse_row_skips_every_unusable_row`, `unit_summarise_skips_unusable_rows_without_a_counter`, `unit_read_records_turns_a_csv_error_into_a_skipped_record` |

## Ambiguity decisions

| Ambiguity | Chosen behaviour | Checks |
| --- | --- | --- |
| AMB-001 | Half-up: an exact half rounds away from zero (`6.25` -> `6.3`) | `amb_001_exact_half_rounds_up` (`6.25`, `6.35`, `6.15`, `2.25`), `amb_001_exact_half_rounds_up_near_one_hundred` (`99.95` -> `100.0`), `amb_001_exact_half_rounds_up_near_zero` (`0.05` -> `0.1`), `amb_001_non_half_values_round_normally`, `unit_render_tenths_rounds_an_exact_half_away_from_zero`, `unit_render_tenths_truncates_below_a_half`, `unit_percentage_uses_points_and_half_up`, `req_004_percentage_grid_matches_half_up` |
| AMB-002 | Merge: every occurrence counts, with passed and total summed into one line | `amb_002_merge_sums_passed_and_total`, `amb_002_merge_percentage_uses_the_summed_counts`, `amb_002_merge_is_not_the_last_row`, `amb_002_merge_is_not_the_first_row`, `amb_002_merge_over_three_occurrences`, `amb_002_merge_still_prints_one_line`, `amb_002_merge_keeps_first_appearance_order`, `unit_summarise_merges_a_repeated_suite` |
| AMB-003 | Skip-silent: skip the row, print nothing about it, still exit 0 | `amb_003_non_numeric_passed_row_is_skipped`, `amb_003_non_numeric_total_row_is_skipped`, `amb_003_empty_count_cells_are_skipped`, `amb_003_quoted_non_numeric_counts_are_skipped`, `amb_003_zero_total_row_is_skipped`, `amb_003_zero_total_written_as_a_decimal_is_skipped`, `amb_003_short_row_is_skipped`, `amb_003_blank_line_is_skipped`, `amb_003_blank_suite_id_is_skipped`, `amb_003_negative_counts_are_skipped`, `amb_003_skipped_rows_do_not_change_any_aggregate`, `amb_003_a_suite_with_only_bad_rows_is_absent`, `amb_003_all_rows_bad_still_exits_zero_with_total_zero`, `amb_003_no_skipped_counter_is_printed`, `unit_parse_row_skips_every_unusable_row`, `unit_read_records_turns_a_csv_error_into_a_skipped_record` |

## Input-format edges

The integration suite also covers quoted fields, extra columns on either side
of the declared ones, CRLF line endings, a UTF-8 BOM, a missing final newline,
a header-only file, an input path containing spaces, and a minimal environment
with no install step.

## Relation coverage

`REL-001` (`derived-ratio`, deciding AMB-001) is checked from both directions:
each printed percentage is recomputed from the line's own printed numerator and
denominator in `req_004_percentage_grid_matches_half_up`, and the exact
one-decimal half-up rendering is checked directly in the `amb_001_*` and
`unit_render_tenths_*` checks.

## Deliberate non-goals

The tests assert the confirmed contract, not behaviour the document did not
decide: they do not reserve the suite name `TOTAL`, do not define a suite id
containing whitespace as a multi-field suite, and do not reject `passed` greater
than `total` (the document only requires a 0-100 percentage in percentage
points and does not make that row unusable).
