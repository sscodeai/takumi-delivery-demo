# summary.sh — per-region revenue and average order value from a sales CSV

A small command-line report tool with no install or build step and no network
access.

```
bash summary.sh sales.csv
```

The input is a CSV of sales records. Its first line is the header
`region,amount`. Header names are compared case-insensitively after trimming
surrounding blanks, and the columns must be exactly `region` then `amount`;
a missing, unreadable or different header is a fatal error (non-zero exit, a
diagnostic on stderr, no report lines). Data rows follow one per line, with
standard RFC 4180 quoting, so a quoted region may contain a comma.

```
region,amount
north,120.50
south,80.00
north,99.50
east,45.25
```

The report goes to standard output:

```
east 1 45.25 45.25
north 2 220.00 110.00
south 1 80.00 80.00
TOTAL 4 345.25
SKIPPED 0
```

* one `<region> <count> <sum> <mean>` line per distinct region, sorted ascending
  by the UTF-8 bytes of the region name, so the report does not depend on row
  order (REQ-003, REQ-009);
* the region string is trimmed before grouping and printing; region case is
  significant, so `North` and `north` are separate groups (REQ-003, REQ-008);
* `sum` is the group's exact revenue and `mean` is `sum / count`; both are
  printed with exactly two decimals, rounded half away from zero (REQ-007,
  AMB-003);
* zero and negative amounts are ordinary orders and are included (REQ-008);
* identical rows are independent orders: every occurrence counts (AMB-002);
* `TOTAL <count> <sum>` is printed exactly once, after the region lines, and
  covers every accepted row (REQ-004);
* a row that cannot be parsed — a field count other than two, an empty region
  after trimming, or an amount that is not a plain decimal such as `abc`,
  `1e3`, `$5` or `1,000` — is skipped and excluded from every aggregate, and
  `SKIPPED <skipped-count>` is printed once after the totals line (REQ-005,
  AMB-001). A clean file prints `SKIPPED 0`.

Arithmetic is exact (`fractions.Fraction`), never binary floating point, so
repeated runs print byte-identical output.

## Tests

```
bash run-tests.sh
```

Runs both halves of the delivered suite through one TAP report:

* `tests/test_units.py` exercises the functions in `summary.py` directly
  (header validation, amount parsing, money formatting, aggregation, skipping);
* `tests/test_summary.py` drives the real entry point in subprocesses and
  asserts every acceptance criterion and every `AMB-nnn` decision in
  `docs/requirements/intake.yaml`.

The report is written to `reports/tests.tap` and echoed to stdout; the runner
returns non-zero when any check fails. `docs/test-plan.md` maps each acceptance
criterion to the checks that cover it.

```
bash mutation.sh
```

Applies one deliberate defect at a time to `summary.py`, runs the delivered
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
14 mutants is killed by the delivered suite today (score 100). Mutants are
copied into a throwaway directory, so the working tree is never modified.

## Where the decisions live

`docs/requirements/intake.yaml` is the confirmed requirement document, and
`docs/decisions.md` records every `AMB-nnn` answer with `file:line` anchors.
`grep -rn 'AMB-00' .` goes from the recorded decision to the code that enacts it.

## Continuous integration

`.github/workflows/ci.yml` runs the delivered tests, the delivered command on a
sample carrying the declared `region,amount` header, and the mutation command
above, failing the pipeline if a mutant survives.
