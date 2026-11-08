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
| AMB-001 | How is the pass percentage rounded to one decimal place? | `half-up`: round half away from zero | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:168`, exact integer division and half test `summary.py:167`-`summary.py:170`, rendering `summary.py:171` |
| AMB-002 | How is a suite name repeated on more than one row reported? | `merge`: sum `passed` and `total` across all its rows into one line | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:194`, aggregation `summary.py:196`-`summary.py:201` |
| AMB-003 | What is printed for a suite whose total is `0`? | `zero-rate`: print the suite line with `0.0` as the percentage | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:163`, branch `summary.py:164`-`summary.py:165` |
| AMB-004 | How is an unparseable data row handled? | `stop-error`: exit non-zero with a message naming the offending line | DEFAULTED (`default:`, policy `document-default`) | comment `summary.py:92`, field-count and count checks `summary.py:93`-`summary.py:121`, diagnostic and exit `summary.py:225`-`summary.py:227` |

## Rules stated directly by the requirement

These are not ambiguities, so they carry no `AMB-` comment; they are listed so
the record is complete.

| id | rule | anchored at |
| --- | --- | --- |
| REQ-001 | `bash summary.sh <csv>` is the root entry point; bad argument or path exits non-zero on stderr | `summary.sh:1`-`summary.sh:23`, `summary.py:217`-`summary.py:230` |
| REQ-002 | the header `suite,passed,total` is consumed, never printed; blank lines ignored; fields trimmed | `summary.py:61`-`summary.py:72`, `summary.py:141`-`summary.py:146`, `summary.py:181`-`summary.py:190` |
| REQ-002 | the declared sample has no header, so a first record that is not the header is data | `summary.py:187`-`summary.py:190` |
| REQ-003 | percentage is `passed/total*100` with exactly one decimal | `summary.py:155`-`summary.py:171` |
| REQ-004 | one line per distinct suite in first-appearance order, then one `TOTAL` line | `summary.py:174`-`summary.py:214` |
| REQ-005 | the three non-mechanised policies follow AMB-002, AMB-003 and AMB-004 | README "Decisions"; the AMB rows above |

The delivered tests that pin these rows are in `tests/test_summary.py`
(acceptance, exact stdout/stderr through `bash summary.sh`),
`tests/test_summary_units.py` (helpers) and `tests/test_contract.py` (entry
point, pipeline, sample and this record).

## Inheritance from previous deliveries

This repository also carries earlier requests' `passrate.sh` / `passrate.py`
with `tests/test_passrate.py` and `tests/test_units.py`, the root
`mutation.sh` / `mutation/` harness, and `node_modules/`. Those files are
different deliverables and were left in place; this document and the
`summary.sh` / `summary.py` deliverable describe only the current
`suite,passed,total` pass-rate report.
