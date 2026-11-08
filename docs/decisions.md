# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (confirmed 2026-11-08 under the
standing authorization recorded in the document's front matter, ref
`docs/authorizations/SA-002.yaml`). Delivery: `bash summary.sh {csv}`.

Every `AMB-nnn` in that document is recorded here with the answer taken and the
`file:line` anchors that enact it. The source marks the same decisions with
one-line greppable comments, so `grep -rn 'AMB-00' .` finds them.

## Provenance

All five answers were taken from the document's own `default:` under the signed
standing authorization (`method: standing-authorization`, signed by SS,
expires 2026-11-11). They are **DEFAULTED** -- a machine's guess, not a
person's choice -- so every row below is one a reviewer may most plausibly want
to revisit. The document marks all five `unmechanised`; no judge checks the
layout, ordering or tolerance they settle yet.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | How is each assignee's open and closed result laid out? | `one-line`: one line per assignee carrying both counts | DEFAULTED (`default:`) | comment `summary.py:104`, line rendered `summary.py:107`; tests `tests/test_summary.py:171`, `tests/test_summary_units.py:82` |
| AMB-002 | In what order do the per-assignee results appear? | `alphabetical`: sorted by name in locale-independent byte order | DEFAULTED (`default:`) | comment `summary.py:101`, sort key `summary.py:102`; tests `tests/test_summary.py:218`, `tests/test_summary_units.py:71` |
| AMB-003 | Which status values count as open and which as closed? | `exact`: only the lowercase tokens `open` and `closed` | DEFAULTED (`default:`) | comment `summary.py:86`-`summary.py:87`, matching `summary.py:88`-`summary.py:93`; tests `tests/test_summary.py:161`, `tests/test_summary_units.py:50` |
| AMB-004 | What happens to a row with an empty assignee or an unrecognised status? | `skip`: ignore the row, continue, no skipped count printed | DEFAULTED (`default:`) | short row `summary.py:62`-`summary.py:64`, empty assignee `summary.py:83`-`summary.py:85`, unrecognised status `summary.py:92`-`summary.py:93`; tests `tests/test_summary.py:154`, `tests/test_summary_units.py:45` |
| AMB-005 | How is an assignee shown whose tickets are all in one status? | `explicit-zero`: the missing category is printed as `0` | DEFAULTED (`default:`) | comment `summary.py:105`-`summary.py:106`, both counts printed `summary.py:107`; tests `tests/test_summary.py:186`, `tests/test_summary_units.py:65` |

The output shape rows that the document does state directly are enacted by
`summary.py:107` (assignee line) and `summary.py:110` (exactly one `TOTAL`
line, printed last). Each rule above is also exercised from the inside in
`tests/test_summary_units.py`; `docs/test-plan.md` maps those checks to the
same `REQ-nnn` and `AMB-nnn` ids.

## Inheritance from previous deliveries

This repository also carries previous requests' `passrate.sh` / `passrate.py`
with `tests/test_passrate.py`, `tests/test_units.py`, the root `mutation.sh`,
the `mutation/` harness and `node_modules/`. Those files are a different
deliverable and were left in place; this document describes only the current
`assignee,status` ticket summary.
