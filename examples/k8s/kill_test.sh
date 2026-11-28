#!/bin/bash
# Run Rolda in a local kind cluster and kill pods while a batch of simulated
# agent sessions is sent. Prints what was found against the ground truth.
#
# Needs: docker, kind, kubectl, uv. Takes a few minutes (it pulls images).
# Usage: [REUSE=1] kill_test.sh [SESSIONS]   (default 200)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
NAME=rolda-test
SESSIONS=${1:-200}
OUT=${OUT:-/tmp/rolda-kill-test}
mkdir -p "$OUT"
K="kubectl --context kind-$NAME -n rolda"

# REUSE=1 keeps the cluster and its secret, and only reapplies the manifests.
if [ -z "${REUSE:-}" ]; then
  kind delete cluster --name "$NAME" >/dev/null 2>&1 || true
  kind create cluster --name "$NAME" --config "$ROOT/deploy/k8s/kind.yaml"
  docker build -q -f "$ROOT/deploy/docker/Dockerfile" -t rolda:dev "$ROOT" >/dev/null
  kind load docker-image rolda:dev --name "$NAME"

  kubectl --context "kind-$NAME" apply -f - <<<'{"apiVersion":"v1","kind":"Namespace","metadata":{"name":"rolda"}}'
  # Random credentials, created here and never written to a file.
  $K create secret generic rolda-secrets \
    --from-literal=CLICKHOUSE_USER=rolda \
    --from-literal=CLICKHOUSE_PASSWORD="$(openssl rand -hex 16)" \
    --from-literal=POSTGRES_USER=rolda \
    --from-literal=POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
    --from-literal=ROLDA_API_TOKEN="$(openssl rand -hex 24)" \
    --from-literal=ROLDA_OTLP_TOKEN="$(openssl rand -hex 24)"
fi
# The agent sends the collector token, read from the Secret, never from a file.
OTLP_TOKEN=$($K get secret rolda-secrets -o jsonpath='{.data.ROLDA_OTLP_TOKEN}' | base64 -d)
kubectl --context "kind-$NAME" apply -k "$ROOT/deploy/k8s/overlays/dev"

$K rollout status statefulset/clickhouse --timeout=600s
$K rollout status statefulset/postgres --timeout=600s
$K rollout status statefulset/rolda-worker --timeout=600s
$K rollout status statefulset/rolda-collector --timeout=600s
$K rollout status deployment/rolda-api --timeout=600s
echo "== cluster ready: $(date -u +%T)"; $K get pods

# The collector must refuse writes without the token and accept them with it.
probe() {
  curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:14318/v1/traces \
    -H 'Content-Type: application/json' "$@" -d '{"resourceSpans":[]}'
}
echo "OTLP without token:    $(probe)   (expect 401)"
echo "OTLP with wrong token: $(probe -H 'Authorization: Bearer wrong')   (expect 401)"
echo "OTLP with the token:   $(probe -H "Authorization: Bearer $OTLP_TOKEN")   (expect 200)"

(
  cd "$ROOT"
  OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20$OTLP_TOKEN" \
  uv run --no-project --with opentelemetry-sdk \
    --with opentelemetry-exporter-otlp-proto-http \
    python examples/support_agent/run.py --seed 83 --sessions "$SESSIONS" \
    --endpoint http://127.0.0.1:14318/v1/traces --truth "$OUT/truth.jsonl" \
    > "$OUT/batch.out" 2>&1
) &
BATCH=$!

# Kills, spread over the run. The first and last are graceful, one is a crash.
sleep 40; echo "$(date -u +%T) delete worker (graceful)";  $K delete pod rolda-worker-0 --wait=false
sleep 50; echo "$(date -u +%T) delete collector-0";         $K delete pod rolda-collector-0 --wait=false
sleep 50; echo "$(date -u +%T) kill worker (crash)";        $K delete pod rolda-worker-0 --grace-period=0 --force --wait=false
sleep 50; echo "$(date -u +%T) delete postgres";            $K delete pod postgres-0 --wait=false
wait "$BATCH" || true
echo "== batch finished: $(date -u +%T)"; tail -9 "$OUT/batch.out"

# Give the worker time to finish the last windows.
for _ in $(seq 1 60); do
  $K get pods --no-headers | grep -v -E "Running|Completed" >/dev/null || break
  sleep 5
done
sleep 150
$K get pods
python3 - "$OUT/truth.jsonl" > "$OUT/q.sql" <<'PY'
import json, sys
ids = [json.loads(line)["trace_id"] for line in open(sys.argv[1])]
print("SELECT trace_id, rule FROM incidents WHERE trace_id IN ("
      + ",".join(f"'{i}'" for i in ids) + ");")
PY
$K exec -i postgres-0 -- sh -c 'psql -U "$POSTGRES_USER" -d rolda -At -F, -f -' \
  < "$OUT/q.sql" > "$OUT/incidents.csv"
python3 - "$OUT" <<'PY'
import collections, json, sys
out = sys.argv[1]
truth = {}
for line in open(out + "/truth.jsonl"):
    row = json.loads(line)
    truth[row["trace_id"]] = row["fault"]
found = collections.defaultdict(set)
for line in open(out + "/incidents.csv"):
    trace_id, rule = line.strip().split(",")
    found[trace_id].add(rule)
expect = {
    "tool_timeout": {"span_error"}, "rate_limit": {"span_error"},
    "tool_loop": {"tool_loop"},
    "latency_outlier": {"latency_outlier", "span_latency_outlier"},
    "token_blowup": {"token_outlier", "span_token_outlier"},
}
print("fault              n  detected")
for fault, rules in expect.items():
    ids = [t for t, f in truth.items() if f == fault]
    hit = [t for t in ids if found[t] & rules]
    print(f"{fault:16} {len(ids):3}  {len(hit):3}")
healthy = [t for t, f in truth.items() if f == "healthy"]
print("healthy", len(healthy), "flagged", sum(1 for t in healthy if found[t]))
PY
$K exec postgres-0 -- sh -c 'psql -U "$POSTGRES_USER" -d rolda -At -c "select count(*) from (select trace_id, rule from incidents group by 1,2 having count(*)>1) d"' | sed 's/^/duplicate incidents: /'
$K exec postgres-0 -- sh -c 'psql -U "$POSTGRES_USER" -d rolda -At -c "select name, cursor from worker_state"'
echo "(delete the cluster with: kind delete cluster --name $NAME)"
