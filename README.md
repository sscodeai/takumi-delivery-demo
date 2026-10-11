# takumi-delivery-demo

Demonstration target for takumi's black-box delivery mode: a confirmed
requirement becomes a delivered product through an independently forged judge, a
pull request, an issue, a pipeline, and a merge.

## The delivered tools

### `summary.sh`, the script shape

`summary.sh` summarises a daily temperature CSV export. It is a Bash entry point
around a Python 3 standard-library program; it reads one local file, writes the
report to stdout and never touches the network.

```sh
bash summary.sh readings.csv
```

The input CSV has the header `date,station,temperature_c`, followed by one
reading per line:

```csv
date,station,temperature_c
2024-01-01,ALPHA,10.4
2024-01-01,BRAVO,-2.5
2024-01-02,ALPHA,11.6
2024-01-02,BRAVO,-1.5
2024-01-03,ALPHA,9.5
```

For that file the tool prints one line per station with at least one valid
reading, then a skipped line and a total line:

```text
ALPHA 3 9.5 11.6 10.5
BRAVO 2 -2.5 -1.5 -2.0
SKIPPED 0
TOTAL 5
```

- A station line is `<station> <count> <min> <max> <mean>`.
- `count` is the number of the station's valid readings.
- `min` and `max` are its smallest and largest `temperature_c`.
- `mean` is the arithmetic mean of its values.
- `min`, `max` and `mean` each carry exactly one decimal place.
- `SKIPPED <count>` counts the malformed rows that were excluded.
- `TOTAL <count>` counts all valid readings (the per-station counts sum to it).

Station lines are emitted in ascending byte-wise station id order.

### Decisions

The script's confirmed requirement document (`docs/requirements/intake.yaml`)
settled five ambiguities; the tool honours all of them, and the service
delivered against `docs/requirements/service-station-summary.yaml` honours the
same chosen options:

| Decision | Chosen option | Behaviour |
| --- | --- | --- |
| AMB-001 | skip-count | Malformed rows are skipped, excluded from every aggregate, and reported on `SKIPPED <count>`. |
| AMB-002 | merge | Every occurrence of a repeated `(date, station)` key is its own reading. |
| AMB-003 | half-up | `min`, `max` and `mean` round half away from zero to one decimal place. |
| AMB-004 | ascending | Station lines are sorted by ascending byte-wise station id. |
| AMB-005 | valid-only | `TOTAL` counts valid readings only. |

A row is well-formed when it has exactly three comma-separated fields, a
non-empty station, a calendar-valid ISO-8601 date (an optional time suffix is
accepted) and a plain decimal temperature. The declared header line
`date,station,temperature_c` is consumed and never counted as a reading; a first
line that is not that header is itself a reading in the declared positional
order, so the pipeline's header-less sample is aggregated rather than dropped.
Malformed rows never abort the run: the process exits 0 after processing a
readable file.

### Why this stack

Bash plus Python 3's standard library needs no install step and runs on any
developer laptop. Temperatures are kept as `Decimal` values and rendered through
exact integer arithmetic, so the half-away-from-zero rule is not distorted by
binary floating point. The tool is fast: a 200,000-row fixture runs in well under
a second here.

### The service shape: `serve.sh`

`serve.sh` is the HTTP service shape of the same summary. It starts a
localhost-only server around the Python 3 standard-library program in
`station_service.py`, reads one CSV at start-up and serves the report at
`/summary`.

```sh
bash serve.sh readings.csv 8731
# in another shell:
curl -fsS http://127.0.0.1:8731/summary
```

The report is one declared output line per JSON object, in ascending byte-wise
station id order, followed by the skipped count and the total:

```text
{"station":"ALPHA","count":3,"min":9.5,"max":11.6,"mean":10.5}
{"station":"BRAVO","count":2,"min":-2.5,"max":-1.5,"mean":-2.0}
{"skipped":0}
{"total":5}
```

Each line is the compact JSON object the requirement document declares in its
``output_format`` shapes, so the whole response body is JSON lines.

The service honours the same confirmed decisions as `summary.sh`: AMB-001
skip-count, AMB-002 merge, AMB-003 half-up rounding, AMB-004 ascending
byte-wise station order and AMB-005 valid-only total. It binds `127.0.0.1`,
makes no outbound network call, keeps the report in memory and answers
`GET /summary` with HTTP 200 `application/json`; every other path answers 404.

## Tests

```sh
bash run-tests.sh
```

The suite drives the real entry point through a process boundary and checks it
against an independent reference implementation
(`tests/reference.py`, exact `Fraction` arithmetic) plus a randomized
permutation/differential property suite, and `tests/test_service.py` starts the
HTTP service through the same process boundary and parses the declared output
lines it serves. Together they cover every requirement and every confirmed
decision in `docs/requirements/intake.yaml` and
`docs/requirements/service-station-summary.yaml`.

## Continuous integration

`.github/workflows/ci.yml` runs the delivered project's own tests
(`bash run-tests.sh`) and starts the service on the requirement document's
sample input, waits for `/summary` to answer, and asserts the response carries
the declared `"total"` line before it stops the service.
