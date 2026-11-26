# Fixtures

Rows follow the `otel_traces` columns and the OpenTelemetry GenAI
attribute names.

| File | Origin |
|---|---|
| `spans_otel_sdk.json` | Produced by a small agent instrumented with the real OpenTelemetry SDK (8 traces, 42 spans). The LLM is a **stub**: model name, token counts and LLM latencies are scripted. Span ids, timestamps, durations and status come from the SDK. No prompt or response text. |
| `spans_genai.json` | Hand-written, **synthetic**. Covers the current attribute names. |
| `spans_legacy.json` | Hand-written, **synthetic**. Covers legacy names, invalid values and trace content that looks like prompt injection. |

Replace the synthetic and stubbed parts with traces captured from a real
agent when one is available.
