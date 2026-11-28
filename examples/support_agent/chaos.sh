#!/bin/bash
# Kill the current leader worker three times while a batch runs. Needs a
# Compose stack with two worker replicas (docker compose up --scale worker=2).
# Usage: chaos.sh LOGFILE
LOG=$1
leader() {
  for c in $(docker ps --filter name=compose-worker --format '{{.Names}}'); do
    v=$(docker exec "$c" python -c "
import urllib.request as u
t=u.urlopen('http://127.0.0.1:9100/metrics',timeout=3).read().decode()
print([l for l in t.splitlines() if l.startswith('rolda_worker_is_leader')][0].split()[-1])" 2>/dev/null)
    [ "$v" = "1" ] && echo "$c" && return
  done
}
for n in 1 2 3; do
  sleep 70
  L=$(leader)
  echo "$(date -u +%T) kill #$n leader=$L" >> "$LOG"
  docker kill "$L" >/dev/null 2>&1
  sleep 8
  docker start "$L" >/dev/null 2>&1
  echo "$(date -u +%T) restarted $L" >> "$LOG"
done
echo "$(date -u +%T) chaos done" >> "$LOG"
