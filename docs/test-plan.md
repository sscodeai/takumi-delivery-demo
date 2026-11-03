# Test plan

Requirement: `docs/requirements/intake.yaml`. Entry point: `bash passrate.sh <csv>`.

`bash run-tests.sh` runs `tests/test_units.py` (functions in `passrate.py`) and
`tests/test_passrate.py` (the real entry point in subprocesses) into one TAP
report. Every check below is executed on every run.

## Acceptance criteria

| id | criterion | checks |
| --- | --- | --- |
| REQ-001 | `bash passrate.sh <sample.csv>` exits 0 | `req_001_exits_zero_and_writes_nothing_to_stderr`, `req_001_declared_sample_report_is_exact` |
| REQ-001 | the script is at the repository root and takes the path as `$1` | `req_001_entry_point_sits_at_the_repository_root`, `req_001_reads_the_path_substituted_as_the_first_argument`, `req_001_declared_sample_report_is_exact` (judge-style path substitution), `req_001_no_argument_is_a_usage_error` |
| REQ-001 | a missing or unreadable path exits non-zero with a stderr diagnostic | `req_001_missing_input_path_is_a_fatal_error`, `req_001_an_unreadable_path_is_a_fatal_error` |
| REQ-001 | nothing on stdout outside the declared shapes | `req_001_stdout_carries_only_declared_shapes`, `extra_a_quoted_suite_containing_a_comma_stays_one_line` |
| REQ-002 | 48/50 prints `96.0`; 17/20 prints `85.0` | `req_002_percentage_has_exactly_one_fractional_digit` |
| REQ-002 | whole percentages keep one fractional digit (`100.0`, `0.0`) | `req_002_percentage_has_exactly_one_fractional_digit` |
| REQ-002 | the percentage is derived from the same line's printed counts | `req_002_percentage_is_derived_from_the_printed_counts`, `rel_001_every_percentage_matches_its_own_printed_counts` |
| REQ-003 | a `total,suite,passed` header yields the sample report | `req_003_reordered_header_yields_the_sample_report` |
| REQ-003 | the header row is never reported as data | `req_003_the_header_row_is_never_reported` |
| REQ-003 | a header missing `suite`/`passed`/`total` exits non-zero naming it | `req_003_a_missing_column_is_fatal_and_named`, `unit_resolve_columns_names_each_missing_column` |
| REQ-003 | extra columns are tolerated | `req_003_extra_columns_are_ignored`, `unit_resolve_columns_ignores_extra_columns` |
| REQ-003 | header names are trimmed and case-insensitive | `req_003_header_names_are_trimmed_and_case_insensitive`, `unit_resolve_columns_ignores_case_and_blanks` |
| REQ-004 | exactly one totals line, after the suite lines | `req_004_totals_line_is_printed_once_and_last_of_the_aggregates`, `req_001_stdout_carries_only_declared_shapes` |
| REQ-004 | the declared sample totals read `TOTAL 165 174` | `req_004_declared_sample_totals_are_165_and_174` |
| REQ-004 | totals are printed for a single suite | `req_004_a_single_suite_still_prints_totals` |
| REQ-004 | totals follow the suite lines even when rows were skipped | `req_004_totals_follow_the_suite_lines_even_when_rows_were_skipped`, `req_001_stdout_carries_only_declared_shapes` |
| REQ-005 | two `auth` rows (48/50, 1/1) print `auth 49 51 96.1` | `req_005_repeated_suite_rows_merge_into_one_line` |
| REQ-005 | one line per distinct suite, not per row | `req_005_line_count_is_distinct_suites_not_rows` |
| REQ-005 | a repeated suite merges only its valid rows | `req_005_merge_uses_valid_rows_only_for_a_repeated_suite` |
| REQ-006 | an unparsable `passed` produces no suite line and `SKIPPED 1` | `req_006_an_unparsable_passed_is_skipped_and_counted` |
| REQ-006 | a clean file prints no `SKIPPED` line | `req_006_a_clean_input_prints_no_skipped_line` |
| REQ-006 | totals sum only counted rows | `req_006_skipped_rows_are_excluded_from_the_totals`, `diff_001_totals_are_the_sum_of_the_counted_rows` |
| REQ-006 | a suite whose only row has `total=0` gets no line and is skipped | `req_006_a_zero_total_suite_gets_no_line_and_is_skipped`, `unit_parse_row_rejects_unusable_rows` |
| REQ-006 | every malformed row shape is skipped once and counted | `amb_003_every_unusable_row_shape_is_skipped_and_counted`, `unit_summarise_counts_each_malformed_shape_once` |

## Decisions

| decision | checks |
| --- | --- |
| AMB-001 half-up | `amb_001_an_exact_half_rounds_away_from_zero`, `amb_001_a_stored_half_at_two_decimals_rounds_up`, `amb_001_a_value_just_below_a_half_rounds_down`, `amb_001_a_half_below_one_percent_rounds_up_to_one_decimal`, `unit_format_percentage_rounds_exact_half_away_from_zero`, `unit_format_percentage_rounds_a_value_just_below_a_half_down`, `unit_format_percentage_rounds_a_half_below_one_percent_up` |
| AMB-002 merge | `req_005_repeated_suite_rows_merge_into_one_line`, `amb_002_merge_sums_both_counts_and_rows`, `unit_summarise_merges_a_repeated_suite` |
| AMB-003 skip-count | `req_006_skipped_rows_are_excluded_from_the_totals`, `amb_003_skip_count_counts_each_unusable_row_once`, `amb_003_every_unusable_row_shape_is_skipped_and_counted`, `unit_summarise_reports_skipped_only_when_something_was_skipped`, `unit_summarise_counts_each_malformed_shape_once` |
| REL-001 derived-ratio | `rel_001_every_percentage_matches_its_own_printed_counts` |
| DIFF-001 independent recomputation | `diff_001_an_independent_pass_yields_the_same_lines`, `diff_001_totals_are_the_sum_of_the_counted_rows` |

## Mutation

`bash mutation.sh` (equivalently `npx stryker run --reporters json`) applies
each defect in `mutation/mutation.py` to `passrate.py` in a throwaway copy and
runs the suite above against it. A survivor fails the harness. The 18 delivered
mutants cover AMB-001, AMB-002, AMB-003 and the REQ-002/003/004/005/006
behaviours they depend on.
