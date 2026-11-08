# summary.sh -- per-suite pass percentage

A small command-line report tool with no install or build step and no network
access. It uses only the Python 3 standard library.

```
bash summary.sh sample/suites.csv
```

For that sample the report is:

```
login 45 50 90.0
search 19 20 95.0
billing 7 8 87.5
TOTAL 71 78
```

## Input

The input is a CSV whose first record is the header `suite,passed,total`:

```
suite,passed,total
login,45,50
search,19,20
billing,7,8
```

* the header is consumed and never printed as a suite;
* each later non-empty line is one record, and blank lines are ignored;
* surrounding whitespace on every field is ignored;
* a header that names the same three columns in another order is resolved by
  name;
* the requirement's declared sample carries no header line, so a first record
  that is not the declared header is read as data in the declared
  `suite,passed,total` order;
* a file with only the header is valid and prints only `TOTAL 0 0`.

## Output

The report contains exactly one line per distinct suite, in the order in which
each suite first appears in the input, followed by exactly one totals line:

```
<suite> <passed> <total> <percentage>
TOTAL <passed_sum> <total_sum>
```

Fields are separated by single ASCII spaces. There is no percent sign and no
header. The percentage is `passed / total * 100` with exactly one digit after
the decimal point. The totals line sums the `passed` and `total` values of the
printed suite lines.

## Decisions

`docs/requirements/intake.yaml` records four ambiguities. All four answers were
taken from the document's own `default:` under the standing authorization in
its front matter; none was chosen by a person. `docs/decisions.md` lists each
answer with `file:line` anchors into `summary.py`, and the source carries
greppable `AMB-00n` comments so `grep -rn 'AMB-00' .` finds the code that
enacts each one.

* **AMB-001 (half-up):** percentages round half away from zero to one decimal,
  so `2/3` prints `66.7` and `1/16` prints `6.3`, not `66.6` or `6.2`.
* **AMB-002 (merge):** when a suite name appears on more than one row, all of
  its rows are summed into one suite line at its first-appearance position.
* **AMB-003 (zero-rate):** a suite whose total is `0` is printed with `0.0` as
  its percentage.
* **AMB-004 (stop-error):** a row with the wrong number of fields, a
  non-integer or negative `passed`/`total`, or `passed` greater than `total`
  stops the run with a non-zero exit and a diagnostic naming the input line;
  no partial report is written to standard output.

A missing argument, a missing or unreadable file, or a directory path prints a
diagnostic on standard error, writes nothing to standard output and exits
non-zero.

## Tests

```
bash run-tests.sh
```

runs the delivered suites and writes TAP reports under `reports/`:

* `tests/test_summary.py` -- acceptance tests that drive `bash summary.sh` in
  subprocesses against `tests/fixtures/` and the declared sample;
* `tests/test_summary_units.py` -- unit tests for the parsing, grouping and
  formatting helpers in `summary.py`;
* `tests/test_contract.py` -- delivery contract checks (entry point, kept
  pipeline, sample, and the decision record).

## Inherited files

This repository is reused between requests. `passrate.sh` / `passrate.py`,
`tests/test_passrate.py`, `tests/test_units.py`, the root `mutation.sh` and
`mutation/` harness, and `node_modules/` belong to earlier, different
deliverables and are left in place. They are not run by `run-tests.sh` and are
not part of this requirement.
