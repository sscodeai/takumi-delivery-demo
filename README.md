# common-keys

A small command-line tool that reads a JSON file holding an array of objects and
prints the keys that appear in **every** one of those objects, one per line, in
ascending Unicode code point order. When no key is common to all of them it
prints the single word `none`.

The **current** confirmed requirement is `docs/requirements/intake.yaml`;
earlier rounds of this repository delivered other families and their documents
are kept under `docs/` for context.

## The delivered product: `common-keys.sh`

The deliverable is a single command:

```sh
bash common-keys.sh <json-file>
```

It reads one local JSON file and writes to stdout:

- exactly those keys present in every object, one per line, sorted by code
  point, or
- the lowercase word `none` when no key is shared.

It exits `0` when it produced an answer (including `none`) and non-zero when it
rejected the input, with a diagnostic on stderr and nothing on stdout.

```sh
$ printf '[{"a":1,"b":2},{"a":3,"b":4}]' > shared.json
$ bash common-keys.sh shared.json
a
b
$ printf '[{"a":1,"b":2},{"a":3,"c":4}]' > partial.json
$ bash common-keys.sh partial.json
a
$ printf '[{"x":1},{"y":2}]' > none.json
$ bash common-keys.sh none.json
none
```

The input is one JSON value and that value must be an array. An array element
that is **not** an object is skipped, so the intersection runs over the object
elements that remain; an array with no object element at all prints `none`.
Anything that is not usable -- a missing or unreadable file, a file that is not
valid UTF-8, a file that does not parse (including the non-standard `NaN` and
`Infinity` literals), or a top-level value that is not an array -- is rejected
with a diagnostic on stderr, a non-zero exit and no key list on stdout.

## The recorded decisions

The confirmed document settles three choices and the implementation applies
each one:

| id | question | chosen |
| --- | --- | --- |
| AMB-001 | an array with no objects | `none`: print the single line `none` and exit 0, because no key is common to all zero objects |
| AMB-002 | a non-object array element | `skip`: ignore the non-object element and intersect the keys of the remaining objects |
| AMB-003 | malformed input | `error`: exit non-zero and print a diagnostic to stderr, producing no result lines |

Only an object's own top-level keys count; a nested object is just another
value and its keys are never flattened into dotted paths. The order is ascending
Unicode code point, so `A` precedes `a`.

## Stack

- `common-keys.sh` -- the declared entry point, a thin Bash wrapper.
- `common_keys.py` -- the JSON parsing and key-intersection logic, using only
  the Python 3 standard library. No install step, no network access, no stdin.
- `tests/common_keys_tests.py` + `run-tests.sh` -- the delivered test suite; it
  drives the entry point and the in-process logic, cross-checks both against an
  independent count-based oracle over random arrays, writes a TAP report to
  `reports/tests.tap` and exits 0 only when every case passes. The runner also
  executes `tests/test_acceptance.py`, which names every acceptance criterion
  and every recorded ambiguity decision.
- `tests/verify_tap_report.py` -- the runner's REQ-005 artifact check: before
  the TAP report is echoed, it must be TAP version 13 with a `1..N` plan, no
  `not ok` point and a zero failure total.
- `mutation.sh` + `mutation/common_keys_mutation.py` -- the declared mutation
  entry point; it mutates `common_keys.py`, runs the delivered suite against
  each mutant, and writes the survivors-json report to
  `reports/mutation/mutation.json`. `mutation/stryker-cli.mjs` is kept as a
  compatibility alias for the older `npx stryker run --reporters json` spelling.
- `.github/workflows/ci.yml` -- the delivery's own pipeline: it runs the test
  suite and reads the TAP report, runs the deliverable on the all-shared,
  partially-shared, none and skipped-element worlds, checks that an unusable
  input is rejected, and checks the mutation report.

## Running the checks

```sh
bash run-tests.sh     # writes reports/tests.tap, exits 0 on green
bash mutation.sh      # writes reports/mutation/mutation.json, exits 0 on no survivors
```

Both commands run offline and use only Python 3 and Bash. `bash mutation-test.sh`,
`bash mutation/run.sh` and `bash scripts/mutation.sh` are compatibility aliases that
run the summary CLI's mutation harness and write the same survivors-json report to
`reports/mutation/mutation.json`.

## Compatibility deliverable: `summary.sh`

Earlier confirmations in this repository declared a per-station CSV temperature
summary, and the host's delivery pipeline still exercises it. The command

```sh
bash summary.sh <csv-file>
```

prints one `<station> <count> <min> <max> <mean>` line per station in ascending
byte-wise id order, then a `SKIPPED <count>` line for malformed rows and a
`TOTAL <count>` line for the valid readings. `tests/test_*.py` is its unittest
suite. It is a compatibility deliverable from an earlier requirement, so the
common-keys `run-tests.sh` gate does not run it; run it directly with
`python3 -m unittest discover -s tests -p 'test_*.py'` when changing
`summary.sh`.
