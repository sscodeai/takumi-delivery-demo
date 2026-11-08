# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (confirmed 2026-11-08 under the
standing authorization `docs/authorizations/SA-002.yaml`, digest recorded in the
document's front matter). Delivery: `bash summary.sh {csv}`.

Every `AMB-nnn` in that document is recorded here with the answer taken and the
`file:line` anchors that enact it. `grep -rn 'AMB-00' summary.py
tests/test_summary.py` finds the same one-line comments in the source.

## Provenance

All four answers were taken from the document's own `default:` under the signed
standing authorization recorded in its front matter (`method:
standing-authorization`, signed by SS, expires 2026-11-11). They are
**DEFAULTED** -- a machine's guess, not a person's choice -- so every row below
is one a reviewer may most plausibly want to revisit. AMB-001..003 are named by
a declared relation (`REL-001`, `REL-003`, `DIFF-001`); AMB-004 is the
document's `unmechanised` entry and has no declared relation, so the code
anchors are its only check.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | What happens to a data row that cannot be read? | `skip-count`: skip it, exclude it from every aggregate, print `SKIPPED <skipped>` | DEFAULTED (`default:`) -- mechanised by REL-001 | rule comment `summary.py:169`, malformed field count `summary.py:172`, blank region `summary.py:178`, non-decimal amount `summary.py:184`, `skipped += 1` `summary.py:173` / `summary.py:179` / `summary.py:187`, `SKIPPED` line `summary.py:223`; tests `tests/test_summary.py:311`, `tests/test_summary.py:330`, `tests/test_summary.py:357` |
| AMB-002 | Is each occurrence of an identical (region, amount) row its own sales record? | `merge`: every occurrence counts, so revenue, order count and average include each repetition | DEFAULTED (`default:`) -- mechanised by REL-003 | rule comment `summary.py:194`, count/sum accumulation `summary.py:196`-`summary.py:197`, one line per region `summary.py:205`; tests `tests/test_summary.py:395`, `tests/test_summary.py:742` |
| AMB-003 | How are revenue and average rounded, and how many decimals are printed? | `half-up`: exactly two decimals, rounding the full-precision value half away from zero | DEFAULTED (`default:`) -- mechanised by DIFF-001 | exact-remainder comparison `summary.py:137`, rounding routine `summary.py:124`, revenue use `summary.py:209`, average use `summary.py:210`, formatting `summary.py:142`; tests `tests/test_summary.py:418`, `tests/test_summary.py:431`, `tests/test_summary.py:724` |
| AMB-004 | Is the region cell trimmed, and is comparison case-sensitive? | `exact-trimmed`: trim surrounding ASCII whitespace, compare case-sensitively, print the trimmed first-seen text | DEFAULTED (`default:`) -- `unmechanised` in the document | rule comment `summary.py:103`, trim routine `summary.py:106`, group key lookup `summary.py:190`, printed id `summary.py:211`; tests `tests/test_summary.py:484`, `tests/test_summary.py:490` |

The output shape rows in the deliverable block are enacted by `summary.py:213`
(region line), `summary.py:223` (SKIPPED line) and `summary.py:226` (TOTAL
line). `SKIPPED` is printed even when zero (REQ-005) and `TOTAL` exactly once
after it (REQ-004). Each rule above is also exercised directly in
`tests/test_summary_units.py`, which imports the implementation instead of
driving the shell entry point; `docs/test-plan.md` maps those unit checks to the
same `REQ-nnn` and `AMB-nnn` ids.

## Rounding versus additivity

REQ-004 and REL-002 require the printed per-region revenues to sum to the
printed `TOTAL` revenue. Each region's own revenue is its exact sum rounded
half-up at two decimals (AMB-003), so the printed total is accumulated from
those already-rounded region cents at `summary.py:219` and printed at
`summary.py:226`. Without that, two sub-cent regions (e.g. `0.005` + `0.005`)
would print `0.01` + `0.01` but a total of `0.01`, breaking REL-002. The check
is `tests/test_summary.py:742`.

## Inheritance from the previous delivery

This repository also carries the previous request's `passrate.sh` /
`passrate.py` with `tests/test_passrate.py`, `tests/test_units.py` and the
mutation harness. They are a different deliverable and were left in place;
`bash run-tests.sh` still runs them. This document describes only the
`summary.sh` delivery.
