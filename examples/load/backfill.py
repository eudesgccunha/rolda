"""Print SQL that fills ClickHouse with synthetic history for the baseline.

The rows look like the ones `load.py` sends, spread over the last N days. They
belong to the service `load-agent` so they can be deleted afterwards:

    ALTER TABLE rolda.otel_traces DELETE WHERE ServiceName = 'load-agent'

Usage (the credentials are read inside the container, not by this script):

    python backfill.py --spans 1500000 --days 7 | docker exec -i \\
      compose-clickhouse-1 sh -c \\
      'clickhouse-client --user "$CLICKHOUSE_USER" \\
       --password "$CLICKHOUSE_PASSWORD" --multiquery'
"""

import argparse

SPANS_PER_TRACE = 6

TEMPLATE = """
INSERT INTO rolda.otel_traces
    (Timestamp, TraceId, SpanId, ParentSpanId, TraceState, SpanName, SpanKind,
     ServiceName, ResourceAttributes, ScopeName, ScopeVersion, SpanAttributes,
     Duration, StatusCode, StatusMessage)
SELECT
    fromUnixTimestamp64Nano(
        toInt64((toUnixTimestamp(now()) - 1200
                 - intDiv(t * {span_seconds}, {traces})) * 1000000000
                + k * 10000000)
    ) AS Timestamp,
    lower(hex(sipHash128('load', t))) AS TraceId,
    lower(hex(sipHash64(t, k))) AS SpanId,
    if(k = 0, '', lower(hex(sipHash64(t, 0)))) AS ParentSpanId,
    '' AS TraceState,
    multiIf(k = 0, 'invoke_agent load-agent',
            k % 2 = 1, 'chat load-sim',
            'execute_tool search_orders') AS SpanName,
    'Client' AS SpanKind,
    'load-agent' AS ServiceName,
    map('service.name', 'load-agent') AS ResourceAttributes,
    '' AS ScopeName,
    '' AS ScopeVersion,
    multiIf(
        k = 0,
        map('gen_ai.operation.name', 'invoke_agent',
            'gen_ai.agent.name', 'load-agent'),
        k % 2 = 1,
        map('gen_ai.operation.name', 'chat',
            'gen_ai.agent.name', 'load-agent',
            'gen_ai.request.model', 'load-sim',
            'gen_ai.usage.input_tokens', toString(300 + rand() % 700),
            'gen_ai.usage.output_tokens', toString(20 + rand() % 180)),
        map('gen_ai.operation.name', 'execute_tool',
            'gen_ai.agent.name', 'load-agent',
            'gen_ai.tool.name', 'search_orders',
            'gen_ai.tool.call.arguments', '{{"customer_id": "C12"}}')
    ) AS SpanAttributes,
    toUInt64(exp(16 + 0.8 * ((rand() + rand() + rand()) / 4294967295 - 1.5)))
        * if(k = 0, 5, 1) AS Duration,
    'Ok' AS StatusCode,
    '' AS StatusMessage
FROM (
    SELECT intDiv(number, {per_trace}) AS t, number % {per_trace} AS k
    FROM numbers({spans})
);
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spans", type=int, default=1_500_000)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    traces = args.spans // SPANS_PER_TRACE
    print(
        TEMPLATE.format(
            spans=traces * SPANS_PER_TRACE,
            traces=traces,
            per_trace=SPANS_PER_TRACE,
            span_seconds=args.days * 86400,
        )
    )


if __name__ == "__main__":
    main()
