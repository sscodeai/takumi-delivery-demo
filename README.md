# summary.sh -- per-assignee open and closed ticket counts

A small command-line report tool with no install or build step and no network
access.

```
bash summary.sh tickets.csv
```

The input is a CSV whose first line is a header naming the columns `assignee`
and `status`, in that order (columns are resolved by name, so the order is not
significant):

```
assignee,status
alice,open
bob,closed
alice,closed
carol,open
```

Every later row is one ticket. The report goes to standard output:

```
alice 1 1
bob 0 1
carol 1 0
TOTAL 2 2
```

* one `<assignee> <open-count> <closed-count>` line per distinct assignee
  (REQ-003, AMB-001), sorted ascending by the UTF-8 bytes of the assignee name
  so the report is independent of locale and of CSV row order (AMB-002);
* an assignee whose tickets are all in one status is still reported and the
  missing count prints as `0` (REQ-003, AMB-005);
* only the exact lowercase tokens `open` and `closed` are recognised; no
  trimming or case folding is applied (AMB-003);
* a data row with an empty assignee, an unrecognised status, or too few
  columns is ignored and affects neither count -- no skipped-row line is
  printed (AMB-004);
* `TOTAL <open-total> <closed-total>` is printed exactly once, after the
  assignee lines (REQ-004). Each total is the sum of the corresponding
  per-assignee counts, so `open-total + closed-total` is the number of
  accepted ticket rows;
* a header-only file prints exactly `TOTAL 0 0` and exits 0; a missing or
  unreadable file exits non-zero with a diagnostic on standard error and no
  report on standard output.

The tool opens the input read-only and never modifies it (REQ-001).

## Open decisions

`docs/requirements/intake.yaml` records five ambiguities. All five were
answered from the document's own `default:` under the standing authorization
recorded in its front matter; none was chosen by a person. **They are
pending human sign-off, and no judge checks these presentation and tolerance
decisions yet** (REQ-007). The defaults currently implemented are:

| id | question | default taken | status |
| --- | --- | --- | --- |
| AMB-001 | layout of each assignee's result | `one-line`: one line per assignee with both counts | pending sign-off |
| AMB-002 | order of the per-assignee results | `alphabetical`: sorted by name, locale-independent byte order | pending sign-off |
| AMB-003 | which status values are recognised | `exact`: only lowercase `open` and `closed` | pending sign-off |
| AMB-004 | empty assignee or unrecognised status | `skip`: ignore the row, continue, no skipped count printed | pending sign-off |
| AMB-005 | an assignee whose tickets are all one status | `explicit-zero`: the missing category prints as `0` | pending sign-off |

`docs/decisions.md` maps each id to the `file:line` that enacts it; the source
marks them with greppable `AMB-00n` comments (`grep -rn 'AMB-00' .`).

## Tests

```
bash run-tests.sh
```

`tests/test_summary.py` drives the real entry point against the checked-in CSV
fixtures in `tests/fixtures/` and asserts the per-assignee open/closed counts
on several distinct assignees, the zero-count case, header handling, the
single totals line and its arithmetic, the skip rules, the sort order, and
that a typical 100,000-row file stays inside the document's 10-second prose
budget. `tests/test_summary_units.py` imports `summary.py` and checks the
helper rules directly. `tests/test_contract.py` reads the resulting TAP
reports, checks the mutation-harness metadata, and asserts that the README and
the confirmed requirement record every AMB-nnn answer and its pending status.
All three write TAP reports (`reports/tests.tap`,
`reports/tests-summary-units.tap` and `reports/tests-contract.tap`) and the
runner exits non-zero if any check fails. `docs/test-plan.md` maps each
acceptance criterion and ambiguity to the checks that cover it.

```
bash tests/mutation.sh
```

The mutation check edits the counting logic in a throwaway copy of the project,
re-runs the delivered suite against each mutant, and writes a survivors report
to `reports/mutation/mutation.json` in the form
`{"total": <int>, "survivors": [{"file": "...", "line": <int>, "description": "..."}]}`.
All mutants must be killed for the check to pass.

## Continuous integration

`.github/workflows/ci.yml` runs `bash run-tests.sh` and then runs the
deliverable against the checked-in `tests/fixtures/mixed.csv`, failing the
pipeline if either step fails.

## Inheritance from earlier deliveries

This repository is reused between requests. It also carries `passrate.sh` /
`passrate.py` with `tests/test_passrate.py`, `tests/test_units.py`, the root
`mutation.sh` and `mutation/`, plus `node_modules/`. Those belong to previous
requests and are left untouched; they are not part of this delivery and are
not run by `run-tests.sh` or `tests/mutation.sh`.
