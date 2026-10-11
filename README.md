# takumi-delivery-demo

Demonstration target for takumi's black-box delivery mode: a confirmed
requirement becomes a delivered product through an independently forged judge, a
pull request, an issue, a pipeline, and a merge.

## The delivered product: the station summary HTTP service

The confirmed requirement is
`docs/requirements/service-station-summary.yaml` (REQ-DOC-002). The deliverable is
a long-running HTTP service, not a script: `bash serve.sh <input.csv> <port>`
starts it on `127.0.0.1:<port>` and it answers `GET /summary` with a JSON body
until it is killed.

```sh
bash serve.sh readings.csv 8787
curl -fsS http://127.0.0.1:8787/summary
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

For that file the endpoint answers with one JSON array carrying one declared
object per line: one station object per station with at least one valid reading,
then the skipped count, then the overall total.

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
- `count` is the number of the station's valid readings.
- `min` and `max` are its smallest and largest `temperature_c`.
- `mean` is the arithmetic mean of its values.
- `min`, `max` and `mean` each carry exactly one decimal place.
- `{"skipped":<count>}` counts the malformed rows that were excluded.
- `{"total":<count>}` counts all valid readings (the per-station counts sum to
  it).
- Station objects are emitted in ascending byte-wise station id order.

The array separators sit on their own lines so every object line is exactly the
shape the requirement document declares, while the whole body stays one valid
JSON document.

### Decisions

The confirmed requirement document settled five ambiguities; the service honours
all of them:

| Decision | Chosen option | Behaviour |
| --- | --- | --- |
| AMB-001 | skip-count | Malformed rows are skipped, excluded from every aggregate, and reported on `{"skipped":<count>}`. |
| AMB-002 | merge | Every occurrence of a repeated `(date, station)` key is its own reading. |
| AMB-003 | half-up | `min`, `max` and `mean` round half away from zero to one decimal place. |
| AMB-004 | ascending | Station objects are sorted by ascending byte-wise station id. |
| AMB-005 | valid-only | `{"total":<count>}` counts valid readings only. |

A row is well-formed when it has exactly three comma-separated fields, a
non-empty station, a calendar-valid ISO-8601 date (an optional time suffix is
accepted) and a plain decimal temperature. The declared header line
`date,station,temperature_c` is consumed and never counted as a reading; a first
line that is not that header is itself a reading in the declared positional
order, so a header-less fixture is aggregated rather than dropped. Malformed rows
never abort the service: the service stays up and keeps answering.

### Why this stack

Bash plus Python 3's standard library needs no install step and runs on any
developer laptop. Temperatures are kept as exact `Fraction` values and rendered
through exact integer arithmetic, so the half-away-from-zero rule is not
distorted by binary floating point. The service binds `127.0.0.1`, makes no
outbound network call and parses the CSV once at start-up, so a year of readings
(about 200,000 rows) is summarised in a couple of seconds and then served from
memory.

## The CLI tool: `summary.sh`

The previous requirement (`docs/requirements/intake.yaml`) delivered a script
with the same aggregation and a text report; it is kept and still tested.

```sh
bash summary.sh readings.csv
```

For the sample above it prints:

```text
ALPHA 3 9.5 11.6 10.5
BRAVO 2 -2.5 -1.5 -2.0
SKIPPED 0
TOTAL 5
```

## Tests

```sh
bash run-tests.sh
```

The suite drives the real entry points through a process boundary: it starts
`serve.sh` on a free port, waits for the declared URL and reads the JSON report
against an independent reference implementation (`tests/reference.py`, exact
`Fraction` arithmetic). It also keeps the previous CLI tool's randomized
permutation/differential property suite and drives `summary.sh` through the same
reference. Together they cover every requirement and every confirmed decision in
the requirement document.

## Continuous integration

`.github/workflows/ci.yml` runs the delivered project's own tests
(`bash run-tests.sh`) and starts the service on a free port with the requirement
document's sample input, waits for the declared URL and asserts the declared JSON
response. The service smoke test is bounded, so a service that never answers
fails the job instead of waiting out the runner's limit.
