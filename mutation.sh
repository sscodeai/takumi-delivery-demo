#!/usr/bin/env bash
# mutation.sh -- the mutation harness the requirement document declares.
#
# docs/requirements/intake.yaml declares the mutation step as:
#
#     mutation:
#       run:           bash mutation.sh
#       report_path:   reports/mutation/mutation.json
#       format:        survivors-json
#       max_survivors: 0
#
# It mutates the delivered implementation (common_keys.py), runs the delivered
# test suite (`bash run-tests.sh`) against each mutant, and writes the
# tool-agnostic survivors-json report to reports/mutation/mutation.json. The
# harness exits non-zero when any mutant survives, and the report is written
# either way.
#
# The logic lives in mutation/common_keys_mutation.py (Python 3 standard
# library only), so this needs no install step and no network access; this
# wrapper is the declared entry point.
set -euo pipefail
cd "$(dirname "$0")"

exec python3 mutation/common_keys_mutation.py "$@"
