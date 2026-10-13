# common-keys

A small command-line tool that reads a JSON file holding an array of objects and
prints the keys that appear in **every** one of those objects, one per line,
sorted in ascending order. When no key is common to all of them it prints the
single word `none`.

The **current** confirmed requirement is `docs/requirements/intake.yaml`;
earlier rounds of this repository delivered other families and their documents
are kept under `docs/` for context.

## The delivered product: `common-keys.sh`

The deliverable is a single command:

```sh
bash common-keys.sh <json-file>
```

It reads one local JSON file and writes to stdout:

- exactly those keys present in every object, one per line, sorted, or
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

The input is one JSON value: an array whose elements are objects. Anything else
-- a file that does not parse, a top-level value that is not an array, or an
array element that is not an object -- is rejected (AMB-002). An array that
holds no objects at all prints `none` and exits zero (AMB-003).

## The recorded decisions

The request leaves four choices open; the confirmed document settles them and
the implementation applies each one:

| id | question | chosen |
| --- | --- | --- |
| AMB-001 | what counts as a key | `top-level`: only the keys directly on each object; nested keys are never flattened into dotted paths |
| AMB-002 | malformed input | `stop-error`: a diagnostic on stderr, a non-zero exit, and no key list on stdout |
| AMB-003 | an array with no objects | `none`: print the single line `none` |
| AMB-004 | ordering of case-different names | `codepoint`: sort by Unicode code point, so uppercase precedes lowercase |

## Stack

- `common-keys.sh` -- the declared entry point, a thin Bash wrapper.
- `common_keys.py` -- the JSON parsing and key-intersection logic, using only
  the Python 3 standard library. No install step, no network access, no stdin.
- `tests/common_keys_tests.py` + `run-tests.sh` -- the delivered test suite; it
  writes a TAP report to `reports/tests.tap` and exits 0 only when every case
  passes.
- `mutation/common_keys_mutation.py` + `mutation/stryker-cli.mjs` -- the
  mutation harness behind the declared `npx stryker run --reporters json`,
  which writes the survivors-json report to `reports/mutation/mutation.json`.
- `.github/workflows/ci.yml` -- the delivery's own pipeline: it runs the test
  suite and reads the TAP report, runs the deliverable on the all-shared,
  partially-shared and none worlds, and checks the mutation report.

## Running the checks

```sh
bash run-tests.sh                         # writes reports/tests.tap, exits 0 on green
npx stryker run --reporters json          # writes reports/mutation/mutation.json
```

Both commands run offline and use only Python 3, Bash and the committed local
`stryker` launcher.
