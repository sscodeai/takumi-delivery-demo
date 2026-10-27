# summary.sh — per-suite pass percentages from a test-run CSV

A small command-line tool with no install or build step and no network access.

```
bash summary.sh records.csv
```

The input is a CSV of test-run records. Its first row is a header naming the
columns `suite`, `passed` and `total`; the columns are located by name, so a
reordered file gives the same answer. (A file without a header row is read in
the declared `suite,passed,total` order.)

The report goes to standard output:

```
auth-service 50 54 92.6
billing 12 12 100.0
search 7 9 77.8
TOTAL 75
```

* one `<suite> <passed> <total> <percentage>` line per distinct suite, in order
  of first appearance (REQ-003);
* `<percentage>` is `passed / total * 100` in percentage points, one decimal
  place, rounded half away from zero (REQ-004, AMB-001);
* `TOTAL <tests>` once, after the suite lines: the summed `total` of the printed
  suite lines (REQ-005);
* a repeated suite is merged into one line whose `passed` and `total` are the
  sums over its rows (AMB-002);
* a row that cannot yield a percentage is skipped silently and the run still
  exits 0 (AMB-003).

Arithmetic is exact (`fractions.Fraction`), so row order and binary floating
point cannot change a printed digit.

## Tests

```
bash run-tests.sh
```

Drives the real entry point and writes the TAP report to `reports/tests.tap`;
exits 0 only when every check passes.

```
bash mutation.sh
```

Applies one deliberate defect at a time to `summary.py`, runs the delivered
suite against each mutant, and writes `reports/mutation/mutation.json`
(`{"total": <int>, "survivors": [...]}`). It exits non-zero if any mutant
survives.

## Where the decisions live

`docs/requirements/intake.yaml` is the confirmed requirement document, and
`docs/decisions.md` records every `AMB-nnn` answer with `file:line` anchors.
`grep -rn 'AMB-00' .` goes from the recorded decision to the code that enacts it.

## Continuous integration

`.github/workflows/ci.yml` runs the delivered tests and the delivered command.
