#!/usr/bin/env bash
# mutation-test.sh -- the earlier name of the mutation-detection harness.
#
# The confirmed requirement document declares the mutation entry point as
# `bash mutation.sh` writing `reports/mutation/survivors.json`; this script is
# the name an earlier delivery recorded (`reports/mutation/mutation.json`).
# Both entry points run the same harness and both report files are written, so
# either name is present and correct.
#
#   run:          bash mutation.sh        (this script: bash mutation-test.sh)
#   report_path:  reports/mutation/survivors.json
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
