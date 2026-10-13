# takumi-delivery-demo

Demonstration target for takumi's black-box delivery mode: a confirmed
requirement becomes a delivered product through an independently forged judge, a
pull request, an issue, a pipeline, and a merge.

The **current** confirmed requirement is `docs/requirements/intake.yaml`: a
grid-map shortest-path command-line tool. Earlier deliveries left two more
artifacts in the tree, both kept and documented at the bottom of this file.

## The delivered product: `pathfind.sh`

The deliverable is a single command:

```sh
bash pathfind.sh <mapfile>
```

It reads one local grid map and writes **exactly one line** to stdout:

- the number of moves on a shortest path from `S` to `E`, or
- the lowercase word `unreachable` when no path exists.

It exits `0` when it produced an answer (including `unreachable`) and non-zero
when it rejected the map, with a diagnostic on stderr.

The map is a rectangle over four characters:

| character | meaning |
| --- | --- |
| `#` | wall |
| `.` | free cell |
| `S` | the single start (passable) |
| `E` | the single exit (passable) |

```text
S....
.....
.....
.....
....E
```

```console
$ bash pathfind.sh map.txt
8
```

A map that is not a rectangle over that alphabet, or that does not hold exactly
one `S` and exactly one `E`, is rejected (AMB-003):

```console
$ printf 'S.\n.E.\n' > bad.txt && bash pathfind.sh bad.txt
pathfind.sh: bad.txt: row 2 is 3 cells wide where row 1 is 2
$ echo $?
1
```

Leading and trailing whitespace, blank lines and CRLF line endings are
normalised away before parsing, so an editor's stray space or blank line is not a
format error.

### Decisions

The confirmed requirement document settled three ambiguities; the tool honours
all of them:

| Decision | Chosen option | Behaviour |
| --- | --- | --- |
| AMB-001 | orthogonal | Only the four edge-adjacent moves (up, down, left, right) are allowed. |
| AMB-002 | edges | The printed number counts moves made, so adjacent `S` and `E` print `1`. |
| AMB-003 | reject | A malformed map exits non-zero with a diagnostic on stderr and prints nothing on stdout. |

### Why this stack

`pathfind.sh` is a thin bash wrapper around `pathfind.py`, which uses only the
Python 3 standard library (no install step, no network access, works on a
developer laptop). The search is a breadth-first search with unit edge costs, so
the first arrival at the exit is a shortest path.

## Tests

```sh
bash run-tests.sh
```

The suite (`tests/pathfind_tests.py`) drives the real entry point through the
process boundary — `bash pathfind.sh <mapfile>` — on hand-built maps and also
unit-tests `parse()`, `shortest()` and `main()`. It writes its TAP report to
`reports/tests.tap` (the path the requirement document names) and exits non-zero
when any case fails. The report ends with `# tests N` / `# pass N` / `# fail N`
so a generic TAP reader can read the totals.

## Mutation

The confirmed document declares the mutation tool as:

```text
npx stryker run --reporters json
```

and the report as the tool-agnostic `survivors-json` shape at
`reports/mutation/mutation.json`, with zero survivors tolerated.

Because the declared report shape is not a mutator-specific one, the project
ships its own `stryker` executable: `node_modules/.bin/stryker` (declared in
`package.json`'s `bin` field) launches `mutation/stryker-cli.mjs`, which runs
`mutation/pathfind_mutation.py`. The harness copies the project into a throwaway
directory, applies one deliberate defect to `pathfind.py` at a time, and runs the
delivered suite against the mutant. A mutant the suite still passes is a
survivor. The command exits non-zero when any mutant survives and always writes
the declared report.

```console
$ npx stryker run --reporters json
...
18 mutant(s), 0 survivor(s)
```

## Continuous integration

`.github/workflows/ci.yml` is the delivery's pipeline and has three jobs:

- `tests` runs the delivered suite (`bash run-tests.sh`);
- `deliverable` writes a reachable and an unreachable map, runs exactly
  `bash pathfind.sh <mapfile>`, diffs both answers, and checks that a malformed
  map is rejected; and
- `mutation` runs `npx stryker run --reporters json` and verifies the declared
  `survivors-json` report measured at least one mutant and left no survivor.

Every job is bounded by `timeout-minutes`, and every long-running command by a
shorter inner `timeout`, so a command that hangs fails its own job instead of
waiting out the runner.

## Historical artifacts

Earlier deliveries of the same demo target left two station-summary shapes in
the tree; they are kept and remain tested by their own suites, but the current
requirement is the grid pathfinder above.

- `summary.sh` — a CLI that prints per-station temperature counts, min, max and
  mean from a `date,station,temperature_c` CSV.
- `serve.sh` + `station_summary.py` — the same summary served as JSON over HTTP.
