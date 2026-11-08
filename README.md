# summary.sh -- total revenue and average order value per region

A small command-line report tool with no install or build step and no network
access.

```
bash summary.sh sales.csv
```

The input is a CSV of sales records whose first line is normally the header
naming the columns `region,amount`:

```
region,amount
North,120.50
North,99.50
South,80.00
```

The header is matched case-insensitively after trimming surrounding blanks, so
` REGION , Amount ` is still the header and is never counted as a data row
(REQ-001). The requirement document's declared sample carries no header line,
so a first line that is not that header is read as data instead of being
dropped -- `North,120.50` is an order, not a header.

The report goes to standard output:

```
East 1 45.25 45.25
North 2 220.00 110.00
South 1 80.00 80.00
TOTAL 4 345.25
```

* one `<region> <count> <sum> <mean>` line per distinct region, sorted ascending
  by the UTF-8 bytes of the region string, so the report does not depend on row
  order (REQ-002, REQ-005, REQ-007);
* `count` is the number of usable rows of that region, `sum` their total revenue
  and `mean` their average order value; count has no decimal point and sum and
  mean always carry exactly two decimal places (REQ-002, REQ-006);
* a repeated region merges into its single line: every row is its own order
  (AMB-002);
* the region key is used verbatim, so `North`, `north` and `North ` are three
  regions (AMB-005);
* `TOTAL <count> <sum>` is printed exactly once, after the region lines, over
  every usable row (REQ-003). A header-only file prints only `TOTAL 0 0.00`
  and exits 0;
* an unusable row -- a field count other than two, an empty or whitespace-only
  region, or an amount that is not a plain decimal -- is skipped and excluded
  from every aggregate, and `SKIPPED <skipped-count>` is printed as the last
  line only when at least one row was skipped (REQ-004, AMB-001). A clean file
  prints no `SKIPPED` line;
* only a plain decimal amount is accepted: optional sign, digits and an
  optional fractional part. `$5.00`, `1,000.50`, `50%`, `1e3`, `.5` and ` 5`
  are unusable rows (AMB-004).

All arithmetic is exact (`fractions.Fraction`), never binary floating point, and
printed values are rounded half away from zero at the second decimal place
(AMB-003). Repeated runs therefore print byte-identical output.

## Tests

```
bash run-tests.sh
```

`tests/test_summary.py` drives the real entry point and covers every acceptance
criterion and every `AMB-nnn` decision in `docs/requirements/intake.yaml`. The
report is written to `reports/tests.tap` and echoed to stdout; the runner
returns non-zero when any check fails. `docs/test-plan.md` maps each acceptance
criterion to the checks that cover it, and `docs/decisions.md` records where
each decision is implemented.

The runner also executes the inherited `passrate` suite from the previous
delivery in this repository (`tests/test_passrate.py`, `tests/test_units.py`),
writing `reports/tests-passrate.tap`; that tool keeps its coverage but is not
part of this requirement.

```
bash mutation.sh
```

`npx stryker run --reporters json` (or `bash mutation.sh`) mutates the inherited
`passrate.py` and reports survivors; it is inherited with that tool and is not
required by this delivery.

## Continuous integration

`.github/workflows/ci.yml` runs `bash run-tests.sh` and then runs
`bash summary.sh takumi-sample.csv` on the sample input the requirement document
declares, failing the pipeline if either step fails.
