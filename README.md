# summary.sh -- total revenue and average order value per region

A small command-line report tool with no install or build step and no network
access.

```
bash summary.sh sales.csv
```

The input is a CSV whose first line is a header naming the columns `region` and
`amount`:

```
region,amount
north,100.00
south,50.00
north,25.50
east,10.25
```

Columns are resolved by header name, so `amount,region` works identically
(REQ-002). Header names are matched after trimming surrounding blanks and
folding case; a header without both required columns is a fatal error.

The report goes to standard output:

```
east 10.25 10.25
north 125.50 62.75
south 50.00 50.00
SKIPPED 0
TOTAL 185.75 4
```

* one `<region> <revenue> <average_order_value>` line per distinct region
  (REQ-003), sorted ascending by the UTF-8 bytes of the region string, so the
  report does not depend on row order (REQ-011);
* `revenue` is the region's amount sum and `average_order_value` is that sum
  divided by the region's counted rows; both always carry exactly two decimals
  (REQ-007);
* the region key is the cell trimmed of surrounding ASCII whitespace and
  compared case-sensitively, so `north`, `North` and ` north ` group as `north`
  and `North` (REQ-008, AMB-004);
* every row is its own sales record: a repeated `(region, amount)` pair adds to
  the region's revenue, order count and average again (REQ-006, AMB-002);
* a row with the wrong field count, a blank region cell or a non-decimal amount
  is skipped, excluded from every aggregate and counted on the `SKIPPED` line
  (REQ-005, AMB-001). `SKIPPED 0` is printed for a clean file;
* `TOTAL <revenue> <orders>` is printed exactly once, after the `SKIPPED` line,
  over every counted row (REQ-004). Its revenue is the sum of the printed
  per-region revenues, so the report adds up exactly (REL-002);
* a header-only file prints exactly `SKIPPED 0` and `TOTAL 0.00 0` and exits 0
  (REQ-010); an empty or unreadable file exits non-zero with a diagnostic on
  standard error and no report on standard output (REQ-012);
* negative (refund) and zero amounts are valid measures, not malformed rows
  (REQ-009).

All arithmetic is exact (`fractions.Fraction` from `decimal.Decimal`), never
binary floating point, and values are rounded half away from zero at the second
decimal place (AMB-003). Repeated runs therefore print byte-identical output.

## Tests

```
bash run-tests.sh
```

`tests/test_summary.py` drives the real entry point and covers every acceptance
criterion and every `AMB-nnn` decision in `docs/requirements/intake.yaml`.
`tests/test_summary_units.py` imports the implementation and unit-tests the
helper rules behind the same criteria and decisions, including exact rounding
and header-resolution edges. The reports are written to `reports/tests.tap` and
`reports/tests-summary-units.tap` and echoed to stdout; the runner returns
non-zero when any check fails. `docs/test-plan.md` maps each acceptance
criterion to the checks that cover it, and `docs/decisions.md` records where
each decision is implemented (grep `AMB-00` in the source).

The runner also executes the inherited `passrate` suite from the previous
delivery in this repository (`tests/test_passrate.py`, `tests/test_units.py`),
writing `reports/tests-passrate.tap`; that tool keeps its coverage but is not
part of this requirement.

```
bash mutation.sh
```

`bash mutation.sh` mutates the inherited `passrate.py` and reports survivors; it
is inherited with that tool and is not required by this delivery.

## Continuous integration

`.github/workflows/ci.yml` runs `bash run-tests.sh` and then runs
`bash summary.sh takumi-sample.csv` on the sample input the requirement document
declares, failing the pipeline if either step fails.
