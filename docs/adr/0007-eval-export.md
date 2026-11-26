# 0007. Eval export from human labels

## Status

Accepted.

## Context

Human labels (ADR 0006 follow-up, migration 003) are the ground truth for
tuning rules and, later, for measuring the judge. The export must be
reproducible, safe to share, and strict enough that a bad file fails loudly.

## Decision

- `rolda export-evals --out FILE` writes one JSON object per line (JSONL).
- Each line is a versioned `EvalCase` (`version: 1`): trace id, rule,
  signature, label, expected outcome and the spans' behavior (name,
  operation, tool name, status, tokens, duration).
- `failure` labels export as `expected: incident`. `false_alarm` labels
  export as `expected: no_incident`. `uncertain` labels are excluded.
- Only human labels are exported. Judge labels are not ground truth.
- Prompt and response content, tool arguments and error messages are never
  exported. Capture is off by default, and the case describes behavior only.
- The parser is strict: missing, extra or wrongly typed fields, a bool
  where an integer is expected, and unknown versions all raise
  `EvalFormatError`. Trace text is always a JSON string, never executed.
- The file is created with mode 0600. The command refuses to overwrite an
  existing file unless `--force` is given.
- Spans come from a new `SpanSource.spans_for_trace` port method. The
  ClickHouse adapter uses a parameterized query.

## Consequences

- Cases cannot reproduce content-dependent failures (for example a bad
  answer). They cover structural behavior: errors, loops, latency, tokens.
- Traces whose spans were already deleted are skipped silently in the count.
- A format change needs a new `version`.
