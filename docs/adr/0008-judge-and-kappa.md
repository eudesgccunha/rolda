# 0008. Judge adapter and kappa measurement

## Status

Accepted.

## Context

The judge gives a second opinion on incidents (SPEC section 6). A judge
that is not measured must not decide anything. The MVP therefore measures
agreement with human labels first and wires the judge into the worker later.

## Decision

- `AnthropicJudge` implements the `Judge` port with the official
  `anthropic` SDK (new dependency, approved). Default model is
  `claude-haiku-5-5`, overridden by `ROLDA_JUDGE_MODEL`. The key comes from
  `ANTHROPIC_API_KEY` and is never logged.
- Trace content is untrusted. It is sent only as escaped text inside a
  `<trace_data>` block, and the system prompt says to treat it as data.
  The judge sees behavior only: spans, tools, status, tokens, durations. It
  never sees prompts, responses, tool arguments or the human label.
- The answer is requested as JSON with a schema and then validated again:
  exact keys, verdict from the enum, reason truncated to 300 characters.
  Invalid output, a refusal or an API error becomes `uncertain`.
- `rolda judge-eval --evals FILE` reads the JSONL export (ADR 0007), runs
  the judge on every case and prints Cohen's kappa, raw agreement, the
  confusion counts and how many answers were `uncertain`.
- `uncertain` answers are left out of kappa and reported apart. The command
  refuses to run with fewer than 30 labeled cases (`--min-cases`), because
  kappa on a tiny set means nothing.
- The judge is not called by the worker in v0.1.

## Consequences

- Each `judge-eval` run costs API tokens, proportional to the case count.
- Kappa depends on the quality and number of human labels. Until enough
  labels exist, no kappa value is published.
- A judge that answers `uncertain` often can look good on kappa. The report
  always shows the uncertain count next to it.
- A published kappa must name the model, the case count and the date.
