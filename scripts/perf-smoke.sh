#!/bin/bash
# Phase 5d latency smoke — hits each key endpoint N times and reports p50/p95.
# Usage:
#   JWT=<bearer-token> BASE=http://localhost:8002 bash scripts/perf-smoke.sh

set -eu

BASE="${BASE:-http://localhost:8002}"
JWT="${JWT:?set JWT env var to a valid admin or PE bearer token}"
ITERS="${ITERS:-50}"

percentile() {
  # $1 = sorted ms, $2 = pct (e.g. 50)
  local pct=$2
  local count
  count=$(printf '%s\n' "$1" | wc -l | tr -d ' ')
  local idx=$(( (count * pct + 99) / 100 ))
  [[ "$idx" -lt 1 ]] && idx=1
  [[ "$idx" -gt "$count" ]] && idx="$count"
  printf '%s\n' "$1" | sed -n "${idx}p"
}

measure() {
  local name="$1" method="$2" path="$3" data="${4:-}"
  local samples=()
  for _ in $(seq 1 "$ITERS"); do
    local start end
    start=$(python3 -c 'import time; print(int(time.perf_counter()*1000))')
    if [[ "$method" == "GET" ]]; then
      curl -sS -o /dev/null -H "Authorization: Bearer $JWT" "$BASE$path" >/dev/null
    else
      curl -sS -o /dev/null -X "$method" -H "Authorization: Bearer $JWT" \
        -H "Content-Type: application/json" -d "$data" "$BASE$path" >/dev/null
    fi
    end=$(python3 -c 'import time; print(int(time.perf_counter()*1000))')
    samples+=("$((end - start))")
  done
  local sorted
  sorted=$(printf '%s\n' "${samples[@]}" | sort -n)
  local p50 p95 avg
  p50=$(percentile "$sorted" 50)
  p95=$(percentile "$sorted" 95)
  avg=$(printf '%s\n' "${samples[@]}" | awk '{s+=$1} END{printf "%.0f", s/NR}')
  printf "%-42s iters=%s avg=%sms p50=%sms p95=%sms\n" "$name" "$ITERS" "$avg" "$p50" "$p95"
}

echo "Target: $BASE"
echo "Iterations per endpoint: $ITERS"
echo "----------------------------------------------------------------"
measure "GET /api/v1/health"           GET  "/api/v1/health"
measure "GET /api/v1/alarms"           GET  "/api/v1/alarms?size=20"
measure "GET /api/v1/skills"           GET  "/api/v1/skills"
measure "GET /api/v1/pipelines"        GET  "/api/v1/pipelines"
measure "GET /api/v1/event-types"      GET  "/api/v1/event-types"
measure "GET /api/v1/execution-logs"   GET  "/api/v1/execution-logs?size=20"
measure "GET /api/v1/mcp-definitions"  GET  "/api/v1/mcp-definitions"
echo "----------------------------------------------------------------"
echo "Python baseline to beat (rule of thumb): p50 < 30ms, p95 < 100ms"
