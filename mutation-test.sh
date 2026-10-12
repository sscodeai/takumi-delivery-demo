#!/usr/bin/env bash
# mutation-test.sh -- the mutation-detection harness for the summary.sh CLI.
#
# Required by docs/requirements/intake.yaml (REQ-005):
#
#   run:          bash mutation-test.sh
#   report_path:  reports/mutation/mutation.json
#   format:       survivors-json   ({"total": <int>, "survivors": [...]})
#   max_survivors: 0
#
# The harness copies the project into a throwaway directory, applies one
# deliberate defect to summary.sh at a time, and runs the delivered CLI test
# suite against the mutant. A mutant the suite still passes is a SURVIVOR, i.e.
# a gap in the tests. The confirmed requirement holds the delivered tests to
# zero survivors.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 mutation/mutation_test.py "$@"
