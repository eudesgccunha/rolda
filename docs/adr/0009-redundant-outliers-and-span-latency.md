# 0009. Redundant outliers and per-span latency

## Status

Accepted. Thresholds are calibrated on simulated data only.

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

## Threshold calibration

`DetectionConfig` now accepts a threshold per rule (`latency_z`,
`span_latency_z`, `token_z`); unset values use the shared `z_threshold`
(3.5). `examples/support_agent/sweep.py` replays the rules on recorded
spans and prints recall and false alarms per threshold.

Two runs with ground truth, the second one never used to choose a value
(310 healthy sessions, baseline of 1022 traces):

| z | latency run 3 | latency run 4 | tokens run 3 | tokens run 4 |
|---|---|---|---|---|
| 2.5 | 8/10 | 10/11 | 10/12 | 10/11 |
| 3.0 | 8/10 | 8/11 | 8/12 | 8/11 |
| 3.5 | 4/10 | 5/11 | 7/12 | 5/11 |

False alarms on healthy sessions: the token rule raised none at any
threshold. The span latency rule raised 7 and 5 at z 2.5, and 1 and 0 at
z 3.0 and above.

Decision: `span_latency_z` = 3.0 and `token_z` = 2.5. The whole-trace
latency rule keeps 3.5. These values fit this simulator (one fault per
session, a 3-6x slow call, a 5-10x token blowup). Re-check them on real,
human-labeled traces before trusting them.

## Consequences

- The numbers come from simulated data and one seed. Small groups (10 and
  12) give wide error bars. They show direction, not production rates.
- Error and loop detection is circular here, because the faults were built
  to match the rules.
- A real token blowup on a looping trace is hidden by the suppression.
  The loop incident is still raised.
- Recall is now about 70-90% on injected outliers, with at most 1 false
  alarm in 300 healthy sessions. It still misses faults close to normal
  variation.
- Thresholds are settable from the environment (`ROLDA_Z_*`,
  `ROLDA_MIN_SAMPLES`, `ROLDA_TOOL_LOOP_REPEATS`). Invalid values stop the
  worker at start. Only the calibrated defaults are tested against data.
- Next: consider a per-span token rule.
