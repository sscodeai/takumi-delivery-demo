# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (confirmed 2026-11-08 under the
standing authorization `docs/authorizations/SA-002.yaml`, digest recorded in the
document's front matter). Delivery: `bash ticket-summary.sh {csv}`.

Every `AMB-nnn` in that document is recorded here with the answer taken and the
`file:line` anchors that enact it. `grep -rn 'AMB-00' ticket_summary.py` finds
the same one-line comments in the source. (The inherited `summary.py` /
`passrate.py` from earlier requests carry `AMB-nnn` comments of their own; this
table and its anchors refer only to the ticket delivery.)

## Provenance

All five answers were taken from the document's own `default:` under the signed
standing authorization recorded in its front matter (`method:
standing-authorization`, signed by SS, expires 2026-11-11). They are
**DEFAULTED** -- a machine's guess, not a person's choice -- so every row below
is one a reviewer may most plausibly want to revisit. No generated judge checks
these; the anchors and the named tests are the check.

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | Which status values count as open and as closed? | `strict`: only case-insensitive `open`/`closed` count; every other value makes the row unusable | DEFAULTED (`default:`) | rule comment `ticket_summary.py:60`, comparison `ticket_summary.py:64`, unrecognised value returns `None` `ticket_summary.py:69`, unusable-row branch `ticket_summary.py:110`; tests `tests/test_ticket_summary.py:309`, `tests/test_ticket_summary_units.py:79` |
| AMB-002 | What happens to a row that cannot be used? | `skip-count`: skip it, exclude it from every count, state the number skipped on stderr, exit 0 | DEFAULTED (`default:`) | wrong-field-count branch `ticket_summary.py:102`-`105`, empty-assignee/status/unknown branch `ticket_summary.py:111`-`113`, stderr diagnostic `ticket_summary.py:159`-`163`; tests `tests/test_ticket_summary.py:347`, `tests/test_ticket_summary.py:363`, `tests/test_ticket_summary_units.py:100` |
| AMB-003 | Are assignee names grouped case-sensitively? | `case-sensitive`: `Alice` and `alice` are two assignees, each printed with the spelling it carries | DEFAULTED (`default:`) | rule comment `ticket_summary.py:115`, trimmed assignee `ticket_summary.py:107`, grouping key `ticket_summary.py:119`; tests `tests/test_ticket_summary.py:383`, `tests/test_ticket_summary_units.py:126` |
| AMB-004 | Do two identical rows describe one ticket or two? | `count-each-row`: every data row is its own ticket, so two identical rows count twice | DEFAULTED (`default:`) | rule comment `ticket_summary.py:117`, per-row accumulation `ticket_summary.py:120`; tests `tests/test_ticket_summary.py:396`, `tests/test_ticket_summary_units.py:136` |
| AMB-005 | Must the CSV reader honour RFC 4180 quoted fields? | `quoted-aware`: honour double-quoted fields, embedded commas and doubled quotes | DEFAULTED (`default:`) | rule comment `ticket_summary.py:76`, RFC 4180 reader `ticket_summary.py:78`; tests `tests/test_ticket_summary.py:406`, `tests/test_ticket_summary.py:421`, `tests/test_ticket_summary_units.py:184` |

## Output shape

`<assignee> <open> <closed>` is emitted at `ticket_summary.py:137` in ascending
UTF-8 byte order (`ticket_summary.py:127`); the single `TOTAL <open-sum>
<closed-sum>` line is emitted at `ticket_summary.py:140` and is always the last
stdout line (`ticket_summary.py:156`). Unusable input exits non-zero with a
stderr diagnostic and no stdout (`ticket_summary.py:153`). The decisions above
are also exercised directly in `tests/test_ticket_summary_units.py`;
`docs/test-plan.md` maps the checks to the same `REQ-nnn` and `AMB-nnn` ids.
