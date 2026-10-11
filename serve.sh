#!/usr/bin/env bash
# serve.sh -- start the station temperature summary HTTP service.
#
# Usage: bash serve.sh <input.csv> <port>
#
# Contract (docs/requirements/service-station-summary.yaml):
#   run:  "bash serve.sh {csv} {port}"
#   read: "curl -fsS {url}"
#   url:  "http://127.0.0.1:{port}/summary"
#
# The command STARTS the service and never exits: the first argument is the CSV
# it serves and the second is the localhost port it binds.  A request to
# /summary answers one compact JSON object per line: a station object per
# station with at least one valid reading, the skipped count and the total.
#
# The aggregation and the HTTP surface live in station_service.py, which uses
# only the Python 3 standard library and makes no outbound network call.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  printf 'usage: bash serve.sh <input.csv> <port>\n' >&2
  exit 2
fi

csv_path="$1"
port="$2"

case "$port" in
  ''|*[!0-9]*)
    printf 'serve.sh: port %s is not a whole number\n' "$port" >&2
    exit 2
    ;;
esac
if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
  printf 'serve.sh: port %s is out of range\n' "$port" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "$script_dir/station_service.py" "$csv_path" "$port"
