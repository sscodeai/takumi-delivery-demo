# Test plan

Requirement: `docs/requirements/intake.yaml`. Entry point: `bash summary.sh <csv>`.
Test entry point: `bash run-tests.sh`.

`bash run-tests.sh` runs three suites and exits nonzero when any check fails:

* `tests/test_summary.py` -- acceptance tests that drive the real
  `bash summary.sh` command in subprocesses against the declared sample and
  the checked-in fixtures in `tests/fixtures/`, written to
  `reports/tests.tap`;
* `tests/test_summary_units.py` -- unit tests that import `summary.py` and
  check the parsing, grouping, rounding and formatting helpers directly,
  written to `reports/tests-units.tap`;
* `tests/test_contract.py` -- delivery contract tests that check the entry
  point, the kept CI pipeline, the shipped sample and the decision record,
  written to `reports/tests-contract.tap`.

## Acceptance criteria

| id | criterion | checks |
| --- | --- | --- |
| REQ-001 | `bash summary.sh <csv>` reads `$1`, exits 0 and writes the report to stdout | `test_declared_sample_with_header_produces_the_required_report`, `test_declared_headerless_sample_is_accepted` |
| REQ-001 | no argument or a missing/unreadable path exits nonzero with a stderr diagnostic and empty stdout | `test_missing_argument_is_a_usage_error`, `test_nonexistent_file_is_an_error`, `test_directory_path_is_an_error` |
| REQ-001 | no network, no interactive input, input only read | `test_input_file_is_not_modified`; `summary.py` uses only the standard library |
| REQ-002 | the header is consumed and never printed | `test_header_text_is_never_emitted_as_a_suite_line`, `test_build_report_with_only_a_header_is_an_empty_report` |
| REQ-002 | a header-only file produces no suite lines (`TOTAL 0 0`) | `test_header_only_file_prints_only_total`, `test_header_only_file_with_blank_lines_prints_only_total`, `test_empty_file_is_an_empty_report` |
| REQ-002 | three valid records produce three suite lines | `test_three_valid_records_produce_three_suite_lines` |
| REQ-002 | blank lines ignored, surrounding whitespace ignored | `test_blank_lines_are_ignored`, `test_surrounding_whitespace_on_fields_is_ignored` |
| REQ-003 | `45/50` prints `90.0`; `2/3` prints `66.7` | `test_declared_sample_with_header_produces_the_required_report`, `test_two_thirds_rounds_half_up_to_66_7`, `test_format_percentage_uses_one_decimal` |
| REQ-003 | every percentage has exactly one decimal place | `test_every_percentage_has_exactly_one_decimal_place` |
| REQ-004 | one line per distinct suite in first-appearance order, then one `TOTAL` line | `test_declared_sample_with_header_produces_the_required_report`, `test_duplicate_suites_merge_in_first_appearance_order`, `test_build_report_prints_first_appearance_order_and_totals` |
| REQ-004 | `TOTAL` is last and additive over the printed suite lines | `test_total_line_is_last_and_sum_of_printed_suite_lines` |
| REQ-004 | no percent sign and no header label | `test_no_line_contains_a_percent_sign`, `test_header_text_is_never_emitted_as_a_suite_line` |
| REQ-005 | the three non-mechanised policies are documented and enacted | `test_readme_documents_each_non_mechanised_policy`; the AMB rows below |

## Ambiguities

| id | answer | checks |
| --- | --- | --- |
| AMB-001 | `half-up`: percentages round half away from zero to one decimal | `test_two_thirds_rounds_half_up_to_66_7`, `test_an_exact_half_rounds_away_from_zero`, `test_format_percentage_rounds_an_exact_half_up` |
| AMB-002 | `merge`: repeated suite names are summed into one line at first appearance | `test_duplicate_suites_merge_in_first_appearance_order`, `test_build_report_merges_repeated_suites` |
| AMB-003 | `zero-rate`: a zero total prints a suite line with `0.0` | `test_zero_total_suite_prints_zero_point_zero`, `test_format_percentage_zero_total_is_zero_point_zero`, `test_build_report_prints_zero_rate_for_a_zero_total` |
| AMB-004 | `stop-error`: an unparseable row stops the run naming its line | `test_malformed_rows_stop_with_a_nonzero_exit_and_name_the_line`, `test_a_late_malformed_row_leaves_no_partial_report`, `test_parse_row_rejects_every_malformed_shape_naming_the_line` |

## Decision record

`test_decisions_document_has_a_row_for_every_ambiguity_with_an_anchor` and
`test_every_ambiguity_has_a_greppable_source_comment` keep
`docs/decisions.md` and the `AMB-00n` source comments in agreement.
