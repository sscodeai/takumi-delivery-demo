# passrate.sh — per-suite pass percentage from a CSV of test-run records

A small command-line report tool with no install or build step and no network
access.

```
bash passrate.sh tests.csv
```

The input is a CSV of test-run records. Its first line is normally the header
naming the columns `suite`, `passed` and `total`, in any order and with any
additional columns:

```
total,suite,passed
50,auth,48
20,billing,17
100,search,99
1,auth,1
3,billing,0
```

Header names are trimmed and compared case-insensitively. The columns are
resolved by name, so their order does not matter, and a header missing any of
the three is a fatal error (non-zero exit, a diagnostic on stderr naming the
missing column, no report lines). Data rows follow one per line, with standard
RFC 4180 quoting.

The requirement document's declared sample carries no header line, so a first
line that is a valid three-field data row is also accepted and read as
`suite,passed,total` (REQ-003's header rules apply to every file that does
carry a header).

The report goes to standard output:

```
auth 49 51 96.1
billing 17 23 73.9
search 99 100 99.0
TOTAL 165 174
```

* one `<suite> <passed> <total> <pct>` line per distinct suite, sorted ascending
  by the UTF-8 bytes of the suite name, so the report does not depend on row
  order;
* all rows naming the same suite are merged into its one line: the printed
  counts are the sums over those rows and the percentage is computed from those
  sums (REQ-005, AMB-002);
* `pct` is `passed / total * 100` with exactly one decimal digit, including
  whole values (`100.0`, `0.0`), rounded half away from zero (REQ-002, AMB-001);
* `TOTAL <passed_sum> <total_sum>` is printed exactly once, after the suite
  lines, over every counted row (REQ-004); the request asks for no overall
  percentage, so it carries none;
* a row that cannot produce a percentage — a field count different from the
  header, a `passed` or `total` that is not a non-negative integer, or
  `total = 0` — is skipped and excluded from every aggregate, and
  `SKIPPED <skipped-count>` is printed as the final line only when at least one
  row was skipped (REQ-006, AMB-003). A clean file prints no `SKIPPED` line.

Percentages are exact integer arithmetic, never binary floating point, so
repeated runs print byte-identical output.

## Tests

```
bash run-tests.sh
```

Runs both halves of the delivered suite through one TAP report:

* `tests/test_units.py` exercises the functions in `passrate.py` directly
  (header detection and resolution, count parsing, row validation, half-up
  percentage formatting, aggregation and skipping);
* `tests/test_passrate.py` drives the real entry point in subprocesses and
  asserts every acceptance criterion and every `AMB-nnn` decision in
  `docs/requirements/intake.yaml`.

The report is written to `reports/tests.tap` and echoed to stdout; the runner
returns non-zero when any check fails. `docs/test-plan.md` maps each acceptance
criterion to the checks that cover it.

```
bash mutation.sh
```

Applies one deliberate defect at a time to `passrate.py`, runs the delivered
suite against each mutant, and writes `reports/mutation/mutation.json`
(`{"total": <int>, "survivors": [...]}`). It exits non-zero if any mutant
survives.

The same engine answers the review's mutation command:

```
npx stryker run --reporters json
```

`npx` resolves project-local bins first, so it runs the delivered
`node_modules/.bin/stryker`. That bin forwards to `mutation/mutation.py`: the
delivery host has no npm registry access, so a real `@stryker-mutator/core`
install cannot be fetched there. The output is Stryker's JSON reporter schema on
stdout (mutants, locations, statuses) and in `reports/mutation/stryker.json`,
and the exit status is non-zero whenever a mutant survives — every one of the
18 mutants is killed by the delivered suite today (score 100). Mutants are
copied into a throwaway directory, so the working tree is never modified.

## Where the decisions live

`docs/requirements/intake.yaml` is the confirmed requirement document, and
`docs/decisions.md` records every `AMB-nnn` answer with `file:line` anchors.
`grep -rn 'AMB-00' .` goes from the recorded decision to the code that enacts it.

## Continuous integration

`.github/workflows/ci.yml` runs the delivered tests and then runs
`bash passrate.sh` on the sample input the requirement document declares,
failing the pipeline if either step fails.
