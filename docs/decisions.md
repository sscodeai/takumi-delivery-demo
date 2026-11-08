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
| AMB-001 | Which status values count as open and as closed, and what happens to any other status value? | `exact-match`: trim and compare case-insensitively against `open` / `closed`; anything else is skipped and reported on stderr | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:64`, matching `summary.py:66`-`summary.py:71`, skip `summary.py:96`-`summary.py:98`, stderr `summary.py:147`-`summary.py:150`; tests `test_status_is_trimmed_and_case_insensitive`, `test_unrecognised_status_is_skipped_and_counted_on_stderr`, `test_classify_status_trims_and_folds_case` |
| AMB-002 | Does each assignee get one line carrying both counts, or one line per assignee-and-status pair? | `one-line-per-assignee`: `<assignee> <open_count> <closed_count>`, no per-status line and no extra summary line | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:132`, rendering `summary.py:134`, loop `summary.py:130`; tests `test_one_line_per_assignee_with_both_counts_and_nothing_else`, `test_format_report_sorts_by_utf8_bytes_and_prints_both_counts` |
| AMB-003 | What happens to a data row whose assignee or status field is empty, and to a file whose header lacks the required columns? | `skip-count`: bad rows are skipped, counted on stderr, run still exits 0; a header without `assignee` and `status` stops with a stderr message and a nonzero exit | DEFAULTED (`default:`, policy `document-default`) | header check comment `summary.py:45`, error `summary.py:48`-`summary.py:51`; short row `summary.py:83`-`summary.py:87`; empty assignee `summary.py:89`-`summary.py:92`; empty/unrecognised status `summary.py:94`-`summary.py:98`; stderr report `summary.py:147`-`summary.py:150`; tests `test_skipped_rows_are_counted_on_stderr_and_do_not_change_counts`, `test_empty_assignee_rows_are_skipped_and_counted`, `test_empty_status_rows_are_skipped_and_counted`, `test_short_rows_are_skipped_and_counted`, `test_header_without_required_columns_stops_the_run` |
| AMB-004 | Are assignee names normalised before grouping, so that spelling variants merge into one line or stay separate? | `trim-case-sensitive`: trim surrounding whitespace, preserve case, so `Alice` and `alice` are two assignees | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:57`, trim `summary.py:59`; tests `test_assignee_is_trimmed_but_case_is_preserved`, `test_normalise_assignee_trims_but_keeps_case` |

## Rules stated directly by the requirement

These are not ambiguities, so they carry no `AMB-` comment; they are listed so
the record is complete:

| id | rule | anchored at |
| --- | --- | --- |
| REQ-002 | columns located by header name, not position | `summary.py:39`-`summary.py:52` |
| REQ-002 | RFC 4180 quoting and LF/CRLF records | `summary.py:107`-`summary.py:109` (stdlib `csv.reader`, `newline=""`) |
| REQ-003 | one status count per counted row, missing class prints 0 | `summary.py:99`-`summary.py:101`, `summary.py:131`-`summary.py:134` |
| REQ-004 | byte-order sort, locale-independent output | `summary.py:128`-`summary.py:130`, UTF-8 bytes written at `summary.py:153`-`summary.py:156` |
| REQ-005 | no line for an assignee never seen; empty report exits 0 | `summary.py:125`-`summary.py:135`, `summary.py:138`-`summary.py:159` |

The delivered tests that pin these rows are in `tests/test_summary.py`
(acceptance, exact stdout/stderr through `bash summary.sh`) and
`tests/test_summary_units.py` (helpers). `docs/test-plan.md` maps them to the
`REQ-nnn` ids.

## Inheritance from previous deliveries

This repository also carries an earlier request's `passrate.sh` / `passrate.py`
with `tests/test_passrate.py`, `tests/test_units.py`, the root `mutation.sh`
and `mutation/mutation.py`, plus `node_modules/`. Those files are a different
deliverable and were left in place; this document describes only the current
`assignee,status` ticket summary, whose files are `summary.sh`, `summary.py`,
`run-tests.sh`, `mutation/run.sh`, `mutation/run.py`, `tests/test_summary.py`,
`tests/test_summary_units.py`, `tests/test_contract.py` and `sample/tickets.csv`.
