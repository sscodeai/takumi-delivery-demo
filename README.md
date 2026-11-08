# summary.sh -- per-assignee open and closed ticket counts

A small command-line report tool with no install or build step and no network
access. It uses only the Python 3 standard library.

```
bash summary.sh sample/tickets.csv
```

The input is a CSV whose first line is a header naming the columns `assignee`
and `status` (columns are resolved by name, so their order and any extra
columns are irrelevant):

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
```

* exactly one `<assignee> <open-count> <closed-count>` line per distinct
  assignee, single-space separated, both counts always printed (REQ-003,
  AMB-002); there is no per-status line and no totals line;
* lines are sorted by the UTF-8 bytes of the assignee name, so the report is
  independent of the locale and of the CSV row order (REQ-004);
* status values are trimmed and compared case-insensitively, so `open`,
  `OPEN` and ` closed ` are recognised; any other value is not counted
  (AMB-001);
* an assignee name is trimmed but keeps its case, so `Alice` and `alice` are
  two assignees with two lines (AMB-004);
* a data row with an empty assignee, an empty or unrecognised status, or too
  few columns is skipped and counted; the number of skipped rows is reported
  on standard error and the run still exits 0 (AMB-003);
* a header-only file, or a file whose rows are all skipped, prints nothing and
  exits 0 (REQ-005);
* a header without both `assignee` and `status`, an empty file, an unreadable
  file or a missing argument prints a diagnostic on standard error, writes
  nothing to standard output and exits nonzero (AMB-003).

The input follows RFC 4180: quoted fields may contain commas, doubled quotes
and embedded newlines, and records may end with LF or CRLF (REQ-002). The
input is opened read-only and never modified.

`sample/tickets.csv` ships with the repository so the documented invocation
works on a clean checkout.

## Decisions

`docs/requirements/intake.yaml` records four ambiguities (AMB-001 to
AMB-004). All four answers were taken from the document's own `default:`
under the standing authorization recorded in its front matter; none was chosen
by a person. They are **DEFAULTED** and are the rows a reviewer may most
plausibly want to revisit.

`docs/decisions.md` maps each id to the `file:line` that enacts it; the source
marks them with greppable `AMB-00n` comments (`grep -rn 'AMB-00' .`).

## Tests

```
bash run-tests.sh
```

`tests/test_summary.py` drives the real entry point against the checked-in CSV
fixtures in `tests/fixtures/` and asserts exact stdout and stderr for mixed
counts, single-status assignees, reordered and extra columns, RFC 4180 quoting,
shuffled rows, byte order, locale independence, header-only and all-skipped
files, skipped-row accounting, and each AMB-001..AMB-004 rule.
`tests/test_summary_units.py` imports `summary.py` and checks the helpers
directly. `tests/test_contract.py` reads the resulting TAP reports, checks the
mutation harness and decision record, and proves that a deliberately broken
expectation and a surviving mutant both make the run fail.
Three TAP reports are written: `reports/tests.tap` is the acceptance/AMB
report, `reports/tests-units.tap` is the unit report, and
`reports/tests-contract.tap` is the delivery contract report. Each suite writes
only its own report, and the runner exits nonzero if any check fails.
`docs/test-plan.md` maps each acceptance criterion and ambiguity to its checks.

```
bash mutation/run.sh
```

The mutation check applies one deliberate defect at a time to `summary.py` (and
one to `summary.sh`) in a throwaway copy of the project, re-runs the delivered
suite against each mutant, and writes a tool-agnostic survivors report to
`reports/mutation/mutation.json` in the form
`{"total": <int>, "survivors": [{"file": "...", "line": <int>, "description": "..."}]}`.
All mutants must be killed for the check to pass, so the delivered tests are
shown to be able to fail.

## Continuous integration

`.github/workflows/ci.yml` runs `bash run-tests.sh`, the mutation check and the
documented deliverable invocation (`bash summary.sh sample/tickets.csv`),
failing the pipeline if any step fails.

## Inheritance from earlier deliveries

This repository is reused between requests. It also carries an earlier
request's `passrate.sh` / `passrate.py` with `tests/test_passrate.py`,
`tests/test_units.py`, the root `mutation.sh` and `mutation/mutation.py`, plus
`node_modules/`. Those belong to previous requests and are left untouched; they
are not part of this delivery and are not run by `run-tests.sh` or
`mutation/run.sh`.
