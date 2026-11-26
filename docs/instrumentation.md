# Instrumenting an agent for Rolda

Rolda reads OpenTelemetry traces that follow the GenAI semantic
conventions. Point your agent's OTLP exporter at the Collector from
`deploy/compose` and Rolda does the rest.

## What to emit

- Service name: set `service.name` to the agent's name.
- Root span: `invoke_agent <name>` with `gen_ai.operation.name=invoke_agent`
  and `gen_ai.agent.name`.
- Model calls: `chat <model>` with `gen_ai.operation.name=chat`,
  `gen_ai.request.model`, `gen_ai.usage.input_tokens` and
  `gen_ai.usage.output_tokens`.
- Tool calls: `execute_tool <tool>` with
  `gen_ai.operation.name=execute_tool` and `gen_ai.tool.name`.
- Failures: set the span status to ERROR with a short message.

Rolda never needs prompt or response text. Leave content capture off.

## Python example

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider(
    resource=Resource.create({"service.name": "support-agent"})
)
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint="http://127.0.0.1:4318/v1/traces")
    )
)
tracer = provider.get_tracer("my_agent")
```

A complete working agent is in `examples/support_agent/`. Its model is
simulated, so it needs no API key. Its tools and control flow are real code.

## Check that traces arrive

```bash
cd deploy/compose
docker compose exec -T clickhouse sh -c \
  'clickhouse-client --user "$CLICKHOUSE_USER" \
   --password "$CLICKHOUSE_PASSWORD" \
   -q "SELECT count(DISTINCT TraceId) FROM rolda.otel_traces"'
```

Then run the worker (see the README) and list the incidents.
