#!/usr/bin/env bash
# mutation.sh -- the mutation-detection entry point for the summary.sh CLI.
#
# This is the entry point the confirmed requirement document declares
# (docs/requirements/intake.yaml, REQ-008 / REL-005):
#
#   mutation:
#     run:           bash mutation.sh
#     report_path:   reports/mutation/survivors.json
#     format:        survivors-json   {"total": <int>, "survivors": [...]}
#     max_survivors: 0
#
# The harness copies the project into a throwaway directory, applies one
# deliberate defect to summary.sh at a time, and runs the delivered CLI test
# suite against the mutant. A mutant the suite still passes is a SURVIVOR, i.e.
# a gap in the tests. The confirmed requirement holds the delivered tests to
# zero survivors, so this command exits non-zero when any mutant survives.
#
# It writes reports/mutation/survivors.json (the path the document names) and
# also reports/mutation/mutation.json for readers of the earlier name.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 mutation/mutation_test.py --report reports/mutation/survivors.json "$@"
