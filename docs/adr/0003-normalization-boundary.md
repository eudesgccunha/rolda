# 0003. Normalization is the only boundary with raw OTel attributes

Status: accepted

## Context

The OpenTelemetry GenAI semantic conventions are not stable. Attribute
names have already changed (for example `gen_ai.usage.prompt_tokens` to
`gen_ai.usage.input_tokens`).

## Decision

- `rolda.traces.normalize` is the only module that reads raw span
  attributes. It accepts current and legacy names.
- The rest of the code uses the domain model in `rolda.traces.model`.
- The model has no prompt or response fields. Content capture is off by
  default and needs redaction before it is stored.
- A row with a missing id or timestamp raises `NormalizationError`. Other
  missing or invalid attributes become `None`.

## Consequences

- A convention change touches one module and its fixtures.
- Callers must handle `NormalizationError` per row, so one bad span does
  not stop a worker window.
