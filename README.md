# ticket-summary.sh -- open and closed support tickets per assignee

A small command-line report tool with no install or build step and no network
access. Python 3 (standard library only) does the work; the shell script is the
entry point.

```
bash ticket-summary.sh tickets.csv
```

The input is a CSV whose first line is a header naming the columns `assignee`
and `status`. Columns are resolved by header name (after trimming and folding
case), so their order and any extra columns do not matter (REQ-002):

```
assignee,status
alice,open
alice,closed
alice,open
bob,open
carol,closed
```

The report goes to standard output:

```
alice 2 1
bob 1 0
carol 0 1
TOTAL 3 2
```

* one `<assignee> <open> <closed>` line per distinct assignee that appears in at
  least one usable data row, printed trimmed and otherwise as read (REQ-003);
* lines are ordered by the UTF-8 bytes of the assignee string, so two runs over
  the same data are directly comparable and row order is irrelevant (REQ-003);
* `TOTAL <open-sum> <closed-sum>` is printed exactly once, last, and its values
  are the column sums of the printed per-assignee lines (REQ-004). A
  header-only file prints exactly `TOTAL 0 0`;
* statuses are compared case-insensitively after trimming surrounding
  whitespace from both cells, so ` Open ` and `CLOSED` are the recognised
  values (REQ-005);
* a row with the wrong number of fields, an empty assignee, an empty status or
  an unrecognised status is unusable: it is skipped, contributes to no count,
  and the number skipped is stated in one diagnostic line on stderr, for
  example `skipped 2 rows`; the tool still exits 0 (REQ-006);
* a missing, unreadable or undecodable file, an empty file, or a header without
  `assignee`/`status` exits non-zero with a diagnostic on stderr and nothing on
  stdout (REQ-001, REQ-002).

## Adopted readings for the open questions (REQ-009)

The requirement document left five readings open. All five were taken from the
document's own `default:` under the signed standing authorization in its front
matter, so they are **DEFAULTED** -- a machine's guess, not a person's choice.
Each is pinned by the named tests in `tests/test_ticket_summary.py` and
`tests/test_ticket_summary_units.py`; `docs/decisions.md` records the answer and
its `file:line` anchors, and the source marks the enacting code with
`AMB-nnn` comments.

| id | question | adopted reading | pinned by |
| --- | --- | --- | --- |
| AMB-001 | Which status values count as open/closed? | **strict**: only case-insensitive `open` and `closed` count; anything else makes the row unusable | `amb001_unrecognised_status_makes_the_row_unusable`, `req005_pending_rows_are_counted_in_neither_column`, `unit_classify_status_rejects_every_other_value` |
| AMB-002 | What happens to a row that cannot be used? | **skip-count**: skip it, exclude it from every count, report the number skipped on stderr, exit 0 | `req006_skipped_diagnostic_is_on_stderr_and_never_on_stdout`, `req006_skipped_count_is_stated_for_a_clean_file_too`, `unit_summarise_skips_every_unusable_shape` |
| AMB-003 | Are assignee names grouped case-sensitively? | **case-sensitive**: `Alice` and `alice` are two assignees, each printed with its own spelling | `amb003_assignee_names_are_compared_case_sensitively`, `unit_summarise_keeps_name_casing_apart` |
| AMB-004 | Do two identical rows describe one ticket or two? | **count-each-row**: every data row is its own ticket, so two identical rows count twice | `amb004_identical_rows_count_as_two_tickets`, `unit_summarise_counts_identical_rows_separately` |
| AMB-005 | Must the reader honour RFC 4180 quoted fields? | **quoted-aware**: double-quoted fields, embedded commas and doubled quotes inside an assignee name are honoured | `amb005_quoted_fields_keep_commas_and_doubled_quotes`, `unit_read_records_honours_quoted_fields` |

## Tests

```
bash run-tests.sh
```

`tests/test_ticket_summary.py` drives the real entry point and writes the TAP
report `reports/tests.tap`; `tests/test_ticket_summary_units.py` imports the
implementation and unit-tests the same rules, writing
`reports/tests-ticket-units.tap`. The runner exits non-zero if any check fails,
and a failing check appears as a `not ok` line in the report.

`docs/test-plan.md` maps each acceptance criterion to the checks that cover it.

## Mutation

```
bash mutation/run-mutation.sh
```

`mutation/ticket_mutation.py` applies one behaviour-changing defect at a time to
`ticket_summary.py` (flipped open/closed counting, dropped totals accumulation,
removed ordering, case-folded grouping, ignored skips, naive CSV splitting, and
more), runs `bash run-tests.sh` against each mutant, and writes
`reports/mutation/mutation.json` in the tool-agnostic shape

```json
{"total": 16, "survivors": []}
```

Against the correct implementation every mutant is killed and the survivors
list is empty. A survivor (a mutant the suite still passes, or one that fails
without writing a `not ok` line into the TAP report) makes the harness exit
non-zero.

## Continuous integration

`.github/workflows/ci.yml` runs `bash run-tests.sh` and then runs the deliverable
as the requirement document declares (`bash ticket-summary.sh {csv}`), failing
the pipeline if either step fails.

## Inheritance from earlier deliveries

This repository is reused between requests and still carries the previous
deliverables (`summary.sh`/`summary.py` for per-region revenue,
`passrate.sh`/`passrate.py` for per-suite pass rates) with their tests and their
`mutation.sh` harness. They are different tools and were left untouched;
`bash run-tests.sh` still runs their suites into separate reports when those
files are present. They are not part of this requirement. `docs/decisions.md`
describes only the `ticket-summary.sh` delivery.
