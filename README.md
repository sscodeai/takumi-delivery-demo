# takumi-delivery-demo

Demonstration target for takumi's black-box delivery mode: a confirmed
requirement becomes a delivered product through an independently forged judge, a
pull request, an issue, a pipeline, and a merge.

The repository holds two delivered shapes of the same station-summary
aggregation, both kept and both tested:

1. the **CLI tool** `summary.sh`, delivered from
   `docs/requirements/intake.yaml` — the current requirement; and
2. the **HTTP service** `serve.sh` + `station_summary.py`, delivered from
   `docs/requirements/service-station-summary.yaml`.

## The delivered product: `summary.sh`

The confirmed requirement is `docs/requirements/intake.yaml`. The deliverable is
a single command: `bash summary.sh <input.csv>` reads one local CSV, writes the
per-station summary to stdout and exits 0 when the file was processed.

```sh
bash summary.sh readings.csv
```

The input CSV is a daily temperature export whose header names the columns
`date`, `station` and `temperature_c`; every following line is one reading:

```csv
date,station,temperature_c
2024-01-01,ALPHA,10.4
2024-01-01,BRAVO,-2.5
2024-01-02,ALPHA,11.6
2024-01-02,BRAVO,-1.5
2024-01-03,ALPHA,9.5
```

For that file the tool prints one line per station, then the skipped count, then
the overall total:

```text
ALPHA 3 9.5 11.6 10.5
BRAVO 2 -2.5 -1.5 -2.0
SKIPPED 0
TOTAL 5
```

- A station line is `<station> <count> <min> <max> <mean>` with single spaces.
- `count` is the number of the station's valid readings.
- `min` and `max` are its smallest and largest `temperature_c`.
- `mean` is the arithmetic mean of its values.
- `min`, `max` and `mean` each carry exactly one digit after the decimal point.
- `SKIPPED <count>` counts the malformed rows that were excluded.
- `TOTAL <count>` counts valid readings only: the per-station counts sum to it.
- Station lines are emitted in ascending byte-wise station id order.

The tool also accepts the requirement document's header-less sample (the columns
are declared in the document): a first line that is not the declared header is
itself a reading in the declared positional order, so a header-less fixture is
aggregated rather than dropped.

### Decisions

The confirmed requirement document settled five ambiguities; the tool honours all
of them:

| Decision | Chosen option | Behaviour |
| --- | --- | --- |
| AMB-001 | skip-count | Malformed rows are skipped, excluded from every aggregate, and reported on `SKIPPED <count>`. |
| AMB-002 | merge | Every occurrence of a repeated `(date, station)` key is its own reading. |
| AMB-003 | half-up | `min`, `max` and `mean` round half away from zero to one decimal place. |
| AMB-004 | ascending | Station lines are sorted by ascending byte-wise station id. |
| AMB-005 | valid-only | `TOTAL` counts valid readings only. |

A row is well-formed when it has exactly three comma-separated fields, a
non-empty station, a calendar-valid ISO-8601 date (an optional time suffix is
accepted) and a plain decimal temperature. A row with another field count, an
empty station, an unparseable date or a non-numeric temperature is malformed: it
is counted on the `SKIPPED` line and never changes a count, min, max or mean.
Malformed rows never abort the run.

### Why this stack

Bash plus Python 3's standard library needs no install step and runs on any
developer laptop. Temperatures are kept as exact rational (`fractions.Fraction`)
values and rendered through exact integer arithmetic, so the half-away-from-zero rule is not
distorted by binary floating point and the accumulated sum is independent of the
row order. The tool reads exactly one local file, makes no network call and
streams the CSV, so a year of readings (about 200,000 rows) is summarised in
well under a second.

## Additional artifact: the station summary HTTP service

The service shape (`docs/requirements/service-station-summary.yaml`,
REQ-DOC-002) is kept as a second delivered artifact. `bash serve.sh <input.csv>
<port>` starts it on `127.0.0.1:<port>` and it answers `GET /summary` with a JSON
body until it is killed.

```sh
bash serve.sh readings.csv 8787
curl -fsS http://127.0.0.1:8787/summary
```

For the sample above the endpoint answers with one JSON array carrying one
declared object per line: one station object per station with at least one valid
reading, then the skipped count, then the overall total.

```json
[
{"station":"ALPHA","count":3,"min":9.5,"max":11.6,"mean":10.5}
,
{"station":"BRAVO","count":2,"min":-2.5,"max":-1.5,"mean":-2.0}
,
{"skipped":0}
,
{"total":5}
]
```

- A station object is
  `{"station":"<station>","count":<count>,"min":<min>,"max":<max>,"mean":<mean>}`.
- `{"skipped":<count>}` counts the malformed rows that were excluded.
- `{"total":<count>}` counts valid readings only.
- Station objects are emitted in ascending byte-wise station id order.

The service uses the same parsing and aggregation rules and the same confirmed
decisions as the CLI tool. It binds `127.0.0.1`, makes no outbound network call
and sums the fixture once at start-up, so it serves a year of readings from
memory.

## Tests

```sh
bash run-tests.sh
```

The suite drives the real entry points through a process boundary: it runs
`bash summary.sh <csv>` on generated fixtures and compares the printed report
against independent reference implementations (`tests/reference.py` with exact
`Fraction` arithmetic and `tests/test_decimal_differential.py` with a
`decimal`/`ROUND_HALF_UP` oracle), and it starts `serve.sh` on a free port, waits for the
declared URL and reads the JSON report against the same reference. It keeps
randomized permutation and differential properties for both shapes, pins the
malformed-row accounting and the rounding rule, and reproduces the exact
fixtures the external acceptance judge builds from the requirement document
(`tests/test_forged_judge_contract.py`). Together they cover every requirement
and every confirmed decision in the requirement document.

### Mutation harness

The confirmed document (`docs/requirements/intake.yaml`) does not ask for a
mutation harness; this is an extra quality gate the delivery adds on top of its
requirements, so that a suite that only looks green cannot pass unnoticed. The
entry point is `bash mutation.sh` (`mutation/mutation_test.py`);
`bash mutation-test.sh` is kept as the earlier name for the same harness. It
copies the project into a throwaway directory,
applies one deliberate defect to `summary.sh` at a time — a broken rounding
boundary, a reversed station order, an accepted malformed row, a lost duplicate
count, a swapped minimum or maximum, a corrupted mean, and so on — and runs the
delivered CLI test suite against each mutant.

It writes the declared `reports/mutation/survivors.json` report in the
`survivors-json` shape (`{"total": <int>, "survivors": [...]}`), and mirrors the
same report to `reports/mutation/mutation.json` for readers of the earlier name,
exiting non-zero when any mutant survives. The harness holds itself to zero
survivors; the report records the mutant count the run measured so a run that
measured nothing cannot look green.

## Continuous integration

`.github/workflows/ci.yml` is the delivery's pipeline and has three jobs:

- `tests` runs the delivered project's own suite (`bash run-tests.sh`);
- `deliverable` feeds the tool the exact world the requirement document
declares, runs it as `bash summary.sh takumi-sample.csv` under a `timeout`, and
diffs the printed report against the declared `ALPHA`/`BRAVO`/`SKIPPED`/`TOTAL`
lines; and
- `mutation` runs the extra mutation gate (`bash mutation.sh`), which must
record zero survivors on `reports/mutation/survivors.json`.

The delivered command is bounded with `timeout`, so a tool that never exits
fails the job instead of waiting out the runner's limit.
