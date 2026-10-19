#!/usr/bin/env bash
# scripts/mutation.sh -- the mutation entry point the confirmed requirement
# document declares (docs/requirements/intake.yaml):
#
#     mutation:
#       run:           bash scripts/mutation.sh
#       report_path:   reports/mutation/mutation.json
#       format:        survivors-json   {"total": <int>, "survivors": [...]}
#       max_survivors: 0
#       timeoutMs:     900000
#
# It runs the same harness as the root `mutation.sh` (`mutation/mutation_test.py`)
# and passes the document's report path explicitly, so a reader of either path
# sees the same survivors-json report. The harness copies the project into a
# throwaway directory, applies one deliberate defect to summary.sh at a time and
# runs the delivered CLI test suite against the mutant. A mutant the suite still
# passes is a SURVIVOR, i.e. a gap in the tests. The document holds the delivered
# suite to zero survivors, so this command exits non-zero when any mutant
# survives; the report is written either way.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 mutation/mutation_test.py --report reports/mutation/mutation.json "$@"
