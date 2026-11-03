# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (confirmed 2026-11-03 under the
standing authorization `docs/authorizations/SA-002.yaml`). Delivery:
`bash passrate.sh {csv}`.

Every `AMB-nnn` in that document is recorded here with the answer taken and the
`file:line` anchors that enact it. `grep -rn 'AMB-00' .` finds the same one-line
comments in the source.

## Provenance

All three answers were taken from the document's own `default:` under the signed
standing authorization recorded in its front matter (`method:
standing-authorization`, `ref: docs/authorizations/SA-002.yaml`, signed by SS,
expires 2026-11-11). They are **DEFAULTED** — a machine's guess, not a person's
choice — and are therefore the rows a reviewer may most plausibly want to
revisit. REL-001 and DIFF-001 mechanise AMB-001; REQ-005 and REQ-006 carry
AMB-002 and AMB-003 as requirement text.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | How is the one-decimal percentage rounded on an exact half? | `half-up`: round half away from zero, so 96.05 becomes 96.1 | DEFAULTED (`default:`) — mechanised by REL-001 / DIFF-001 | rule comment `passrate.py:136`, exact integer scaling `passrate.py:135`, the `>=` that sends a half up `passrate.py:139`, exactly one printed decimal `passrate.py:141`; tests `tests/test_passrate.py:433`, `tests/test_passrate.py:439`, `tests/test_passrate.py:445`, `tests/test_passrate.py:451`, `tests/test_units.py:146` |
| AMB-002 | When the same suite name appears on several rows, which occurrence wins? | `merge`: every row of that suite counts, so passed and total are summed into one line | DEFAULTED (`default:`) — requirement text REQ-005 | rule comment `passrate.py:205`, passed sum `passrate.py:207`, total sum `passrate.py:208`; one line printed per distinct suite at `passrate.py:215`; tests `tests/test_passrate.py:376`, `tests/test_passrate.py:460`, `tests/test_units.py:170` |
| AMB-003 | What happens to a data row that cannot yield a percentage? | `skip-count`: skip the row, exclude it from the totals, report it on a `SKIPPED` line | DEFAULTED (`default:`) — requirement text REQ-006 | malformed definition `passrate.py:110` (field count `passrate.py:116`, non-integer/negative counts `passrate.py:120`, zero total `passrate.py:122`), rule comment `passrate.py:195`, `skipped += 1` `passrate.py:198`, the `SKIPPED` line `passrate.py:228`; tests `tests/test_passrate.py:407`, `tests/test_passrate.py:470`, `tests/test_passrate.py:482`, `tests/test_units.py:191` |

## Where the declared relations are checked

| relation | checked by |
| --- | --- |
| REL-001 derived-ratio (AMB-001) | `tests/test_passrate.py` `rel_001_every_percentage_matches_its_own_printed_counts` (recomputes each printed percentage from that line's own printed passed/total, half-up) |
| DIFF-001 independent recomputation (AMB-001) | `tests/test_passrate.py` `diff_001_an_independent_pass_yields_the_same_lines`, `diff_001_totals_are_the_sum_of_the_counted_rows` |
| mutation-detection | `npx stryker run --reporters json` → `node_modules/.bin/stryker` → `mutation/mutation.py` (18 mutants on `passrate.py`, real `bash run-tests.sh` runs; exit non-zero on a survivor) |
