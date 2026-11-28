# 0017. Baseline built from slices, in the background

## Status

Accepted. It replaces the idea, in the M8 plan, of computing the baseline with
SQL in ClickHouse.

## Context

The worker read 7 days of spans into Python objects every hour and normalized
them in one piece. A measurement with synthetic history showed about 1.36 KB
of memory per span at peak (719 MiB for 500,000 spans, 2,044 MiB for
1,500,000), linear, and a window blocked for the whole read (11.7 s and
36.7 s). At 10 spans per second that is about 8 GB, and at 100 about 80 GB.

Computing the statistics in SQL would have removed the memory, but it needs a
second copy of the normalization in the database: the attribute fallbacks, the
operation map, token parsing and the "root is a span with no parent, or whose
parent is missing" rule, which cannot be written without a self-join. Two
copies drift apart, and ADR 0003 says raw attributes are read in one place.

## Decision

- The history is read in slices of `baseline_slice` (15 minutes), through the
  same `SpanSource` and the same normalization as everything else.
- For each slice only floats are kept (`BaselineSamples`, one 8 byte value per
  sample, durations and tokens of single spans on the log scale). A slice
  never holds `Span` objects after it is summarized.
- The baseline is the merge of the slices of the last `baseline_span` (7 days)
  into `Stats` per group: count, median, MAD and mean absolute deviation. The
  score is computed from those four numbers and equals the score computed from
  the raw samples (tested on random data).
- A refresh reads only the slices it does not have and drops the oldest ones,
  so an hourly refresh costs about an hour of spans. Slices read before an
  error are kept, so a retry continues.
- Refreshing runs as a background task. A window never waits for it. The first
  window after a start runs with an empty baseline, so outlier rules stay quiet
  until the first refresh finishes. Errors and loops do not use the baseline.
- A trace without its root span (cut by a slice edge) is left out of the
  baseline, because its first span would stand in for the whole trace.
- Only complete slices that end at least `lag` before the window are used.

## Evidence

Same synthetic history, before and after: 500,000 spans, 719 MiB to 52 MiB;
1,500,000 spans, 2,044 MiB to 66 MiB; window blocked 11.7 s and 36.7 s to
0.025 s. The memory is nearly flat, and about 14 bytes per span above the
interpreter's own size (an estimate from these two points).

## Consequences

- Building the whole baseline from nothing is slower (28 s and 52 s against
  12 s and 37 s), because it is 672 small queries. It happens once at start,
  in the background. At 100 spans per second a cold start would take on the
  order of 25 minutes (an extrapolation, not a measurement).
- Until the first refresh ends, outlier rules do not fire. Traces are read
  again by the next windows for `lag`, so most are judged once the baseline is
  ready.
- The baseline can be up to `baseline_refresh` plus `lag` old.
- Nothing is persisted. A restart builds it again.
