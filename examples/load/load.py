"""Send healthy-looking agent traces to an OTLP/HTTP Collector at a set rate.

No OpenTelemetry package is needed: it posts OTLP JSON directly, so the
generator itself is not the bottleneck. Each trace has 6 spans: one agent
span, three model calls and two tool calls, like the simulated support agent.

Usage: load.py --rate 100 --seconds 120
"""

import argparse
import http.client
import json
import math
import random
import secrets
import time

SPANS_PER_TRACE = 6
AGENT = "load-agent"


def _span(
    trace_id: str,
    span_id: str,
    parent: str,
    name: str,
    start_ns: int,
    duration_ns: int,
    attributes: dict[str, str],
) -> dict[str, object]:
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "parentSpanId": parent,
        "name": name,
        "kind": 3,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(start_ns + duration_ns),
        "status": {"code": 1},
        "attributes": [
            {"key": k, "value": {"stringValue": v}}
            for k, v in attributes.items()
        ],
    }


def _trace(rng: random.Random, now_ns: int) -> list[dict[str, object]]:
    trace_id = secrets.token_hex(16)
    root_id = secrets.token_hex(8)
    spans: list[dict[str, object]] = []
    offset = 0
    for k in range(1, SPANS_PER_TRACE):
        duration = int(math.exp(rng.gauss(16.0, 0.4)))
        span_id = secrets.token_hex(8)
        if k % 2:
            name = "chat load-sim"
            attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.agent.name": AGENT,
                "gen_ai.request.model": "load-sim",
                "gen_ai.usage.input_tokens": str(rng.randint(300, 1000)),
                "gen_ai.usage.output_tokens": str(rng.randint(20, 200)),
            }
        else:
            name = "execute_tool search_orders"
            attributes = {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.agent.name": AGENT,
                "gen_ai.tool.name": "search_orders",
                "gen_ai.tool.call.arguments": '{"customer_id": "C12"}',
            }
        spans.append(
            _span(
                trace_id,
                span_id,
                root_id,
                name,
                now_ns + offset,
                duration,
                attributes,
            )
        )
        offset += duration
    root = _span(
        trace_id,
        root_id,
        "",
        f"invoke_agent {AGENT}",
        now_ns,
        offset,
        {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": AGENT},
    )
    return [root, *spans]


def _post(
    endpoint: tuple[str, int, str], spans: list[dict[str, object]]
) -> bool:
    host, port, path = endpoint
    body = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": AGENT},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {"scope": {"name": "load"}, "spans": spans}
                    ],
                }
            ]
        }
    )
    conn = http.client.HTTPConnection(host, port, timeout=15)
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        response.read()
        return response.status == 200
    except OSError:
        return False
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=float, default=10.0, help="spans/s")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4318)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    rng = random.Random(args.seed)  # noqa: S311 - simulation, not crypto
    endpoint = (args.host, args.port, "/v1/traces")
    traces_per_second = args.rate / SPANS_PER_TRACE
    owed = 0.0
    sent = failed = 0
    started = time.monotonic()
    for second in range(args.seconds):
        tick = started + second
        owed += traces_per_second
        count = int(owed)
        owed -= count
        now_ns = time.time_ns()
        spans = [span for _ in range(count) for span in _trace(rng, now_ns)]
        if spans:
            if _post(endpoint, spans):
                sent += len(spans)
            else:
                failed += len(spans)
        time.sleep(max(0.0, tick + 1 - time.monotonic()))
    elapsed = time.monotonic() - started
    print(
        f"sent {sent} spans in {elapsed:.0f}s "
        f"({sent / elapsed:.1f}/s), failed {failed}"
    )


if __name__ == "__main__":
    main()
