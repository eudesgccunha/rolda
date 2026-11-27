-- Rolda M3b: incidents. One incident per trace and rule, which makes
-- reprocessing a window idempotent.
CREATE TABLE IF NOT EXISTS incidents (
    trace_id    text        NOT NULL,
    rule        text        NOT NULL,
    span_id     text        NOT NULL,
    evidence    text        NOT NULL,
    confidence  text        NOT NULL CHECK (confidence IN ('high', 'low')),
    detected_at timestamptz NOT NULL,
    PRIMARY KEY (trace_id, rule)
);
