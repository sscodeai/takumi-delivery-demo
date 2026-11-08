# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (confirmed 2026-11-08 under the
standing authorization `docs/authorizations/SA-002.yaml`, digest recorded in the
document's front matter). Delivery: `bash summary.sh {csv}`.

Every `AMB-nnn` in that document is recorded here with the answer taken and the
`file:line` anchors that enact it. `grep -rn 'AMB-00' summary.py
tests/test_summary.py` finds the same one-line comments in the source.

## Provenance

All five answers were taken from the document's own `default:` under the signed
standing authorization recorded in its front matter (`method:
standing-authorization`, signed by SS, expires 2026-11-11). They are
**DEFAULTED** -- a machine's guess, not a person's choice -- so all five are the
rows a reviewer may most plausibly want to revisit.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | What happens to an unusable data row? | `skip-count`: skip it, exclude it from every aggregate, print `SKIPPED <skipped-count>` | DEFAULTED (`default:`) -- mechanised by REL-001 | rule comment `summary.py:195`, unusable-row definition `summary.py:98` (field count `summary.py:107`, blank region `summary.py:93`, non-plain amount `summary.py:112`), `skipped += 1` `summary.py:198`, the `SKIPPED` line `summary.py:240`; tests `tests/test_summary.py:316`, `tests/test_summary.py:323`, `tests/test_summary.py:362`, `tests/test_summary.py:371` |
| AMB-002 | When a region key repeats, what does the report do? | `merge`: every row is its own order, all rows of the region form one aggregate | DEFAULTED (`default:`) -- requirement text REQ-005 | rule comments `summary.py:203` and `summary.py:208`, first-row insert `summary.py:205`, count/sum accumulation `summary.py:207`, `summary.py:210`; one line per distinct region `summary.py:217`; tests `tests/test_summary.py:391`, `tests/test_summary.py:513` |
| AMB-003 | How do sums and means round past the second decimal? | `half-up`: round half away from zero at the second decimal place | DEFAULTED (`default:`) -- mechanised by DIFF-001 | rule comment `summary.py:156`, exact-remainder comparison `summary.py:158`, rounding routine `summary.py:145`, sum use `summary.py:222`, mean use `summary.py:223`; tests `tests/test_summary.py:426`, `tests/test_summary.py:431`, `tests/test_summary.py:444`, `tests/test_summary.py:618`, `tests/test_summary.py:566` |
| AMB-004 | How is the amount field parsed? | `plain-decimal`: optional sign, digits, optional fraction; nothing else -- no symbol/thousands/percent stripping, no surrounding-blank stripping | DEFAULTED (`default:`) | regex `summary.py:44` with rule comment `summary.py:40`, parser `summary.py:72`, applied to the row `summary.py:112`; tests `tests/test_summary.py:591`, `tests/test_summary.py:596`, `tests/test_summary.py:323`, `tests/test_summary.py:348` |
| AMB-005 | Is the region key normalised before grouping? | `exact`: the region field is used verbatim, so case and spacing distinguish regions | DEFAULTED (`default:`) | rule comment `summary.py:89`, verbatim return `summary.py:95`, used as the group key at `summary.py:202`; tests `tests/test_summary.py:406`, `tests/test_summary.py:601` |

The output shape rows in the deliverable block are enacted by `summary.py:224`
(region line), `summary.py:235` (TOTAL line) and `summary.py:240` (SKIPPED
line); `TOTAL` is printed only once and after every region line.

## Rounding versus additivity

REL-003 says the printed per-region sums add up to the printed `TOTAL` sum,
while REQ-006 says a region's sum is its own raw total rounded. Those can only
disagree for sub-cent inputs (two regions of `0.005` each). The `TOTAL` sum is
therefore the sum of the already-rounded region sums (`summary.py:231`,
`summary.py:235`), so REL-003 holds exactly for every input; per-region values
still follow REQ-006 and AMB-003 literally. The check is
`tests/test_summary.py:513`.

## Inheritance from the previous delivery

This repository also carries the previous request's `passrate.sh` / `passrate.py`
with `tests/test_passrate.py`, `tests/test_units.py` and the mutation harness.
They are a different deliverable and were left in place; `bash run-tests.sh`
still runs them. This document describes only the `summary.sh` delivery.
