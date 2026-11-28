#!/bin/bash
# Send load at a rate for a while and sample the worker every 10 seconds.
# Usage: live_load.sh RATE_SPANS_PER_SECOND SECONDS
set -u
RATE=$1; SECONDS_TOTAL=$2
HERE=$(cd "$(dirname "$0")" && pwd)
worker=compose-worker-1
python3 "$HERE/load.py" --rate "$RATE" --seconds "$SECONDS_TOTAL" > "$HERE/.load.out" 2>&1 &
LOAD=$!
echo "t_s window_s lag_s mem windows_ok windows_err incidents"
t=0
while kill -0 "$LOAD" 2>/dev/null || [ $t -lt $((SECONDS_TOTAL + 70)) ]; do
  mem=$(docker stats --no-stream --format '{{.MemUsage}}' "$worker" | awk '{print $1}')
  m=$(docker exec "$worker" python -c "
import urllib.request as u
t=u.urlopen('http://127.0.0.1:9100/metrics',timeout=3).read().decode()
g=lambda p: next((l.split()[-1] for l in t.splitlines() if l.startswith(p)), '-')
print(g('rolda_worker_window_duration_seconds'), g('rolda_worker_lag_seconds'), g('rolda_worker_windows_total{result=\"ok\"}'), g('rolda_worker_windows_total{result=\"error\"}'), g('rolda_worker_incidents_total'))" 2>/dev/null)
  set -- $m
  echo "$t ${1:--} ${2:--} $mem ${3:--} ${4:-0} ${5:--}"
  sleep 10; t=$((t + 10))
done
wait "$LOAD"; cat "$HERE/.load.out"
