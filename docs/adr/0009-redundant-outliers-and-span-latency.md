# 0009. Redundant outliers and per-span latency

## Status

Accepted. Thresholds are still uncalibrated.

## Context

A first run of the simulated support agent (`examples/support_agent`, model
simulated, tools real) exposed two problems in the outlier rules:

- Sessions that loop or fail are naturally longer and heavier. In one run,
  14 of 17 latency outliers and 15 of 22 token outliers were on traces that
  already had a `tool_loop`. One cause raised several incidents.
- `LatencyOutlier` compares the whole trace. A single slow model call among
  several spans barely changes the total, so it was mostly missed.

## Decision

- `suppress_redundant` drops outlier findings (`latency_outlier`,
  `token_outlier`, `span_latency_outlier`) when the same trace has a
  `span_error` or `tool_loop` finding. The worker applies it per trace.
- New rule `SpanLatencyOutlier`. The baseline now keeps durations per
  (agent, operation, tool or span name). Each model or tool span is scored
  against its own group using the robust z-score on the log of the
  duration, because durations are right-skewed. The worst span becomes the
  finding. Groups with fewer than `min_samples` are ignored.
- `LatencyOutlier` (whole trace) stays enabled. It added no unique
  detection in the measured run, but it also raised no false alarm, and it
  covers slowness spread over many spans.

## Evidence

A run with ground truth (400 sessions, seed 31, baseline from two earlier
runs of 300 sessions each):

| Injected fault | Injected | Detected |
|---|---|---|
| tool timeout | 30 | 30 |
| rate limit | 5 | 5 |
| tool loop | 14 | 14 |
| latency outlier | 10 | 4 |
| token blowup | 12 | 7 |

1 of 329 healthy sessions was flagged (`span_latency_outlier`). No outlier
incident was a duplicate of a loop or an error.

## Consequences

- The numbers come from simulated data and one seed. Small groups (10 and
  12) give wide error bars. They show direction, not production rates.
- Error and loop detection is circular here, because the faults were built
  to match the rules.
- A real token blowup on a looping trace is hidden by the suppression.
  The loop incident is still raised.
- Recall for localized faults is still low. Next: sweep `z_threshold` on
  recorded data, and consider a per-span token rule.
