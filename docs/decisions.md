# Decisions and where they live

Requirement: `docs/requirements/intake.yaml` (delivery `bash common-keys.sh {json}`).

Every `AMB-nnn` in that document is recorded here with the answer taken and the
source anchor that enacts it. `file:line` anchors point into the delivered tree
at this commit; `grep -rn 'AMB-00' .` finds the same one-line comments in the
code.

## Front-matter provenance

The run was confirmed under a signed standing authorization, recorded in this
document's front matter (`confirmation.authorization.ref: SA-002.yaml`, signed
by SS, expires 2026-11-11). All three answers below were therefore taken from the
document's own `default:`: they are **DEFAULTED** (chosen by a machine), not
picked by a person. They are the rows a reviewer may most plausibly want to
revisit.

## intake.yaml

| id | question (one line) | answer | provenance | anchored at |
| --- | --- | --- | --- | --- |
| AMB-001 | What when the top-level array is empty (zero objects)? | `none`: print the single word `none` and exit 0 | DEFAULTED (`default:`) | `common_keys.py:91` (no object means empty intersection), `common_keys.py:136` (renders `none`), test `tests/common_keys_tests.py:577` |
| AMB-002 | What with array elements that are not JSON objects? | `skip`: ignore the element, intersect the remaining objects | DEFAULTED (`default:`) | `common_keys.py:89` (object filter), test `tests/common_keys_tests.py:586` |
| AMB-003 | What when the file is missing, unreadable, not JSON, or the top level is not an array? | `error`: non-zero exit, diagnostic on stderr, no result lines | DEFAULTED (`default:`) | `common_keys.py:66` (invalid JSON), `common_keys.py:70` (top level not an array), `common_keys.py:116` (missing/unreadable file), `common_keys.py:120` (not UTF-8), `common_keys.py:129` (InputError writes stderr and returns 1), test `tests/common_keys_tests.py:643` |

Notes:

- AMB-001 and AMB-002 interact: an array whose only elements are non-objects has
  zero object elements, so it also prints `none` (AMB-002 skip, then AMB-001).
  The anchors for both are `common_keys.py:89` and `common_keys.py:91`.
- AMB-003 must not print a result line, so every rejection path returns before
  the stdout write at `common_keys.py:132`; `bash common-keys.sh` is a thin
  `exec` wrapper (`common-keys.sh:25`) and adds no output of its own.

## Not part of this requirement

`summary.sh` also carries `AMB-001` .. `AMB-005` comments. Those belong to the
earlier document `docs/requirements/service-station-summary.yaml`, not to
`intake.yaml`; they are a compatibility deliverable and are not decisions of
this run.
