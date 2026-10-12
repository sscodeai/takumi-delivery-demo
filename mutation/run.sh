#!/usr/bin/env bash
# mutation/run.sh -- the mutation-detection tool for the CLI deliverable.
#
# The requirement document (docs/requirements/intake.yaml) declares:
#   mutation:
#     run: "bash mutation/run.sh"
#     report_path: "reports/mutation.json"
#     format: survivors-json
#     max_survivors: 0
#
# It copies the project, applies one deliberate defect to summary.sh at a time,
# runs the delivered tests against the mutant and writes the survivor report.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 mutation/mutation_test.py "$@"
