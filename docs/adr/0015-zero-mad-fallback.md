# 0015. Outlier score when the MAD is zero

## Status

Accepted. It changes the rule in the original plan, which said to ignore a MAD
of zero.

## Context

A code review pointed out that a group whose history is constant never alerts.
If a summarizer call always uses 1200 tokens, the MAD is 0, the score was
undefined and every outlier rule skipped it. A bug that sent 90,000 tokens
raised nothing. Constant values are common: fixed prompts, coarse timers.

## Decision

`robust_z` keeps the modified z-score when the MAD is above zero. When it is
zero it uses a standard deviation estimate instead: 1.253314 times the mean
absolute deviation, but never less than 5% of the median. The score is then
`(value - median) / scale`.

- A constant history of 1200 gives a scale of 60. A value of 1230 scores 0.5
  and is normal. A value of 1500 scores 5 and 90,000 scores about 1,480.
- The score is still undefined, and the rule skips the group, when there is no
  scale at all, for example a history of zeros.
- The 5% floor is a judgment, not a measurement. It is a named constant
  (`_MIN_RELATIVE_SPREAD`) and should be revisited with real data.

## Consequences

- A group with no variation now alerts on a large change. Some of those
  alerts will be real deployments (a new prompt size), not failures.
- The thresholds calibrated in ADR 0009 are unaffected where the MAD was
  already above zero, which is every group in the simulated runs.
