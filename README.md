# summary.sh -- per-region revenue and average order value

A small command-line report tool with no install or build step and no network
access. It uses only the Python 3 standard library.

```
bash summary.sh sample/sales.csv
```

The input is a CSV whose first record names the columns `region` and `amount`
(columns are resolved by name, so their order and any extra columns are
irrelevant):

```
region,amount
North,120.50
South,80.25
North,99.50
East,45.00
```

The requirement's declared sample ships **without** a header row
(`sample/sales.csv`), so a first record that names neither `region` nor
`amount` is treated as the first data row with the columns in `region,amount`
order. A headered file and the declared headerless sample produce the same
report.

The report goes to standard output:

```
East 1 45.00 45.00
North 2 220.00 110.00
South 1 80.25 80.25
TOTAL 4 345.25
SKIPPED 0
```

* exactly one `<region> <count> <sum> <mean>` line per region present in the
  accepted records, single-space separated (REQ-003);
* region lines are sorted by the UTF-8 bytes of the region name, so the order
  is lexicographic, locale-independent and independent of CSV row order
  (REQ-003, REQ-008);
* `sum` is the region's total revenue and `mean` is `sum / count`, its average
  order value (REQ-003);
* exactly one `TOTAL <count> <sum>` line follows the region lines and carries
  only those two numbers -- no overall mean (REQ-004);
* exactly one `SKIPPED <skipped-count>` line is always last, even when the
  count is 0 (REQ-005);
* every sum and mean has exactly two decimal places, with no thousands
  separator and no currency symbol; counts are plain integers (REQ-006);
* a data row with a non-numeric amount, an empty region, or too few columns
  is skipped, excluded from every aggregate and counted on `SKIPPED`
  (AMB-001);
* a repeated region+amount row is a separate order: it counts twice and both
  amounts are added (AMB-002);
* a per-region mean is rounded half away from zero to two decimals
  (AMB-003);
* a well-formed negative amount is a refund and is included like any other
  record, reducing the region's revenue (AMB-004);
* blank lines between records are neither records nor skipped rows (REQ-002);
* a header-only file (or an empty file, or a header followed only by blank
  lines) is a valid empty report: `TOTAL 0 0.00` then `SKIPPED 0`, exit 0
  (REQ-009);
* a missing argument, an unreadable path, or a header that does not name both
  columns prints a diagnostic on standard error, writes nothing to standard
  output and exits nonzero (REQ-001).

The input follows RFC 4180: quoted fields may contain commas, doubled quotes
and embedded newlines, and records may end with LF or CRLF. The input is
opened read-only and never modified.

`sample/sales.csv` ships with the repository so the documented invocation
works on a clean checkout.

## Tests

```
bash run-tests.sh
```

runs the delivered suites and writes a TAP report to `reports/tests.tap`:

* `tests/test_summary.py` -- acceptance tests that drive `bash summary.sh` in
  subprocesses against `tests/fixtures/` and the declared sample;
* `tests/test_summary_units.py` -- unit tests for the aggregation and
  formatting helpers in `summary.py`;
* `tests/test_contract.py` -- delivery contract checks (TAP reports, the
  wrong-aggregate failure, the decision record).

`bash mutation/run.sh` applies one deliberate defect at a time to
`summary.py` and re-runs the suite; it writes
`reports/mutation/mutation.json` and fails if any mutant survives.

## Decisions

`docs/requirements/intake.yaml` records four ambiguities (AMB-001 to
AMB-004). All four answers were taken from the document's own `default:`
under the standing authorization recorded in its front matter; none was chosen
by a person. `docs/decisions.md` lists each answer with `file:line` anchors
into `summary.py`, and the source carries greppable `AMB-00n` comments so
`grep -rn 'AMB-00' .` finds the code that enacts each one.

## Inherited files

This repository is reused between requests. `passrate.sh` / `passrate.py`,
`mutation.sh` / `mutation/mutation.py`, `tests/test_passrate.py`,
`tests/test_units.py` and `node_modules/` belong to earlier, different
deliverables and are left in place; they are not run by `run-tests.sh` and are
not part of this requirement.
