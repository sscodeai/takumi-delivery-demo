# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (confirmed 2026-10-29 under
`docs/authorizations/SA-002.yaml`). Delivery: `bash summary.sh {csv}`.

Every `AMB-nnn` in that document is recorded here with the answer taken and the
`file:line` anchors that enact it. `grep -rn 'AMB-00' .` finds the same one-line
comments in the source.

## Provenance

All three answers were taken from the document's own `default:` under the signed
standing authorization recorded in its front matter (`method:
standing-authorization`, `ref: docs/authorizations/SA-002.yaml`, signed by SS,
expires 2026-11-11). They are **DEFAULTED** — a machine's guess, not a person's
choice — and are therefore the rows a reviewer may most plausibly want to
revisit. All three are blocking decisions; REL-001, REL-002 and DIFF-001
mechanise them.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | What should the tool do with a data row it cannot parse (wrong field count, empty region, non-numeric amount)? | `skip-count`: skip the row, exclude it from every aggregate, and report it on a `SKIPPED` line | DEFAULTED (`default:`) — mechanised by REL-001 | `summary.py:154` (rule comment), `summary.py:157` (`skipped += 1`), `summary.py:187` (the `SKIPPED` line); malformed definition at `summary.py:83`, `summary.py:86`, `summary.py:88`; RFC 4180 failures become malformed rows at `summary.py:125`; tests `tests/test_units.py:159`, `tests/test_units.py:420`, `tests/test_summary.py:436`, `tests/test_summary.py:477` |
| AMB-002 | When two data rows are identical (same region and same amount), how are they treated? | `merge`: every occurrence counts as its own order | DEFAULTED (`default:`) — mechanised by REL-002 | `summary.py:164` (rule comment), `summary.py:167` (row count grows), `summary.py:168` (sum adds each amount); tests `tests/test_units.py:199`, `tests/test_summary.py:500` |
| AMB-003 | How are printed sums and means rounded to two decimal places? | `half-up`: round half away from zero | DEFAULTED (`default:`) — mechanised by DIFF-001 | `summary.py:106` (rule comment), `summary.py:109` (the `>=` that sends an exact half up), `summary.py:113` (exactly two printed decimals); tests `tests/test_units.py:109`, `tests/test_summary.py:537` |
