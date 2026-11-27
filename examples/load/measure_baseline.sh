#!/bin/bash
# Measure the worker while it builds its baseline from N synthetic spans.
# Usage: measure_baseline.sh N_SPANS
# Needs the Compose stack with the `app` profile and one worker (compose-worker-1).
set -euo pipefail
N=$1
HERE=$(cd "$(dirname "$0")" && pwd)
CH='clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD"'
worker=compose-worker-1

docker exec compose-clickhouse-1 sh -c "$CH -q \"ALTER TABLE rolda.otel_traces DELETE WHERE ServiceName = 'load-agent' SETTINGS mutations_sync = 2\""
python3 "$HERE/backfill.py" --spans "$N" --days 7 \
  | docker exec -i compose-clickhouse-1 sh -c "$CH --multiquery"
rows=$(docker exec compose-clickhouse-1 sh -c "$CH -q \"SELECT count() FROM rolda.otel_traces WHERE ServiceName = 'load-agent'\"")
echo "history rows: $rows"

peak=$HERE/.peak.txt
: > "$peak"
docker restart "$worker" >/dev/null
started=$(date +%s)
while true; do
  mem=$(docker stats --no-stream --format '{{.MemUsage}}' "$worker" 2>/dev/null | awk '{print $1}')
  echo "$mem" >> "$peak"
  built=$(docker exec "$worker" python -c "
import urllib.request as u
t=u.urlopen('http://127.0.0.1:9100/metrics',timeout=3).read().decode()
print([l.split()[-1] for l in t.splitlines() if l.startswith('rolda_worker_baseline_build_seconds')][0])" 2>/dev/null || true)
  [ -n "$built" ] && [ "$built" != "0" ] && break
  [ $(( $(date +%s) - started )) -gt 600 ] && { echo "timeout"; exit 1; }
done
docker exec "$worker" python -c "
import urllib.request as u
t=u.urlopen('http://127.0.0.1:9100/metrics',timeout=3).read().decode()
for l in t.splitlines():
    if l.startswith(('rolda_worker_baseline_build_seconds','rolda_worker_baseline_traces','rolda_worker_window_duration_seconds')): print(l)"
python3 - "$peak" <<'PY'
import sys, re
vals = []
for line in open(sys.argv[1]):
    m = re.match(r"([\d.]+)([KMG]i?B)", line.strip())
    if m:
        n = float(m.group(1)); u = m.group(2)
        vals.append(n * {"KiB": 1/1024, "MiB": 1, "GiB": 1024, "B": 1/1024**2, "KB": 1/1024, "MB": 1, "GB": 1024}[u])
print(f"peak worker memory: {max(vals):.0f} MiB over {len(vals)} samples")
PY
