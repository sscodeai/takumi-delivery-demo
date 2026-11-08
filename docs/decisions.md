# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (confirmed 2026-11-08 under the
standing authorization recorded in the document's front matter, ref
`docs/authorizations/SA-002.yaml`). Deliverable: `bash summary.sh {csv}`.

Every `AMB-nnn` in that document is recorded below with the answer taken, its
provenance, and the `file:line` anchors that enact it. The source marks the
same decisions with one-line greppable comments, so `grep -rn 'AMB-00' .`
finds them.

## Provenance

All four answers were taken from the document's own `default:` under the
signed standing authorization (`method: standing-authorization`, signed by SS,
expires 2026-11-11). They are **DEFAULTED** -- a machine's guess, not a
person's choice -- so every row below is one a reviewer may most plausibly want
to revisit. The document records no human-chosen answer for any of them.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | What happens to a data row that cannot be used as a sales record (non-numeric amount, or missing region/amount field)? | `skip-count`: skip the row, exclude it from every aggregate, count it on `SKIPPED` | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:114`, short row `summary.py:116`-`summary.py:119`, empty region / bad amount `summary.py:121`-`summary.py:125`, line printed `summary.py:172`; tests `test_malformed_rows_are_skipped_counted_and_excluded_from_totals`, `test_short_row_is_skipped_and_counted`, `test_empty_region_is_skipped_and_counted`, `test_summarise_records_skips_and_counts_malformed_rows` |
| AMB-002 | When the same region and the same amount appear on two rows, how is that repetition resolved? | `merge`: each row is its own order, so both rows count and both amounts are added | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:126`, count `summary.py:129`, sum `summary.py:130`; tests `test_identical_rows_are_merged_into_the_aggregates`, `test_summarise_records_merges_identical_rows` |
| AMB-003 | How is a per-region average order value rounded when it has more than two decimal places? | `half-up`: round half away from zero to exactly two decimal places | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:143`, quantize `summary.py:146`, mean division `summary.py:134`-`summary.py:138`, mean printed `summary.py:163`-`summary.py:166`; tests `test_mean_with_more_than_two_decimals_rounds_half_up`, `test_mean_at_an_exact_half_rounds_away_from_zero`, `test_format_amount_rounds_half_up` |
| AMB-004 | How is a well-formed negative amount (a refund) treated? | `include`: count it as a normal record so it reduces the region's revenue total | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:97`, parse `summary.py:85`-`summary.py:99`, included by the only reject test `summary.py:123`; tests `test_negative_amount_is_included_as_a_refund`, `test_parse_amount_accepts_negative_refunds` |

## Rules stated directly by the requirement

These are not ambiguities, so they carry no `AMB-` comment; they are listed so
the record is complete:

| id | rule | anchored at |
| --- | --- | --- |
| REQ-002 | columns located by header name, extra columns and order ignored | `summary.py:52`-`summary.py:76` |
| REQ-002 | declared sample has no header, so a data-first file uses `region,amount` order | `summary.py:195`-`summary.py:203` |
| REQ-002 | blank lines are neither records nor skipped rows | `summary.py:79`-`summary.py:83`, `summary.py:112`-`summary.py:113` |
| REQ-003 | one line per region, sorted, `<region> <count> <sum> <mean>` | `summary.py:153`-`summary.py:166` |
| REQ-004 | exactly one `TOTAL <count> <sum>`, no overall mean | `summary.py:167`-`summary.py:170` |
| REQ-005 | `SKIPPED <n>` always printed last | `summary.py:171`-`summary.py:172` |
| REQ-006 | sums and means with exactly two decimals | `summary.py:141`-`summary.py:151` |
| REQ-008 | byte-identical stdout for shuffled rows | `summary.py:158`-`summary.py:160` |
| REQ-009 | header-only (or empty / blank-only) file is an empty report, exit 0 | `summary.py:183`-`summary.py:209`, `summary.py:167`-`summary.py:172` |
| REQ-001 | bad argument/path/header: stderr diagnostic, empty stdout, nonzero exit | `summary.py:63`-`summary.py:76`, `summary.py:212`-`summary.py:233` |

The delivered tests that pin these rows are in `tests/test_summary.py`
(acceptance, exact stdout/stderr through `bash summary.sh`) and
`tests/test_summary_units.py` (helpers). `docs/test-plan.md` maps them to the
`REQ-nnn` ids.

## Inheritance from previous deliveries

This repository also carries an earlier request's `passrate.sh` / `passrate.py`
with `tests/test_passrate.py`, `tests/test_units.py`, the root `mutation.sh`
and `mutation/mutation.py`, plus `node_modules/`. Those files are a different
deliverable and were left in place; this document describes only the current
`region,amount` revenue summary, whose files are `summary.sh`, `summary.py`,
`run-tests.sh`, `mutation/run.sh`, `mutation/run.py`,
`tests/test_summary.py`, `tests/test_summary_units.py`,
`tests/test_contract.py` and `sample/sales.csv`.
