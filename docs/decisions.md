# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` — delivery `bash summary.sh {csv}`.

Every `AMB-nnn` in that document is recorded here with the answer taken and the
`file:line` anchors that enact it. `grep -rn 'AMB-00' .` finds the same one-line
comments in the source.

## Provenance

This run was confirmed under the signed standing authorization recorded in the
document's front matter (`confirmation.authorization.ref: SA-002.yaml`, signed
by SS, expires 2026-11-11). All three answers below were therefore taken from
the document's own `default:`: they are **DEFAULTED** (a machine's guess, not a
person's choice), and are the rows a reviewer may most plausibly want to
revisit. AMB-001 is the only answer a judge relation checks today (`REL-001
derived-ratio`, `checkedAs: half-up`); AMB-002 and AMB-003 are recorded there as
unmechanised, but the delivered tests do cover them.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | How are percentages rounded when the exact value falls on a half at the one-decimal boundary? | `half-up`: round half away from zero (6.25 becomes 6.3) | DEFAULTED (`default:`) — checked by REL-001 | `summary.py:66` (rule comment), `summary.py:69` (the `>=` that sends an exact half up), `summary.py:83` (percentage scaled to tenths before rounding); covered by `tests/test_summary.py:437` (integration) and `tests/test_units.py:90` (unit) |
| AMB-002 | When the suite key repeats across several rows, what does one line per suite mean? | `merge`: every occurrence counts, summing passed and total into one line | DEFAULTED (`default:`) — unmechanised in the document | `summary.py:154` (rule comment), `summary.py:156` (passed is summed, not replaced), `summary.py:157` (total is summed), `summary.py:161` (one line per suite); covered by `tests/test_summary.py:530` (integration) and `tests/test_units.py:172` (unit) |
| AMB-003 | What happens to a row that cannot yield a percentage (non-numeric passed or total, or total of 0)? | `skip-silent`: skip the row, print nothing about it, still exit 0 | DEFAULTED (`default:`) — unmechanised in the document | `summary.py:108` (rule comment), `summary.py:119` (blank suite id), `summary.py:121` (non-numeric passed/total), `summary.py:125` (total of zero), `summary.py:127` (negative counts, which cannot express a 0..100 percentage); covered by `tests/test_summary.py:569` and `tests/test_summary.py:650` (integration) and `tests/test_units.py:149` (unit) |
