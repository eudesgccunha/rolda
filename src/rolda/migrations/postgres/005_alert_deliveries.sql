-- Alert outbox. One row per incident and channel, written in the same
-- transaction as the incident, so an alert is never lost between "saved" and
-- "sent". A delivery is retried until it works or runs out of attempts.
CREATE TABLE IF NOT EXISTS alert_deliveries (
    trace_id        text        NOT NULL,
    rule            text        NOT NULL,
    channel         text        NOT NULL,
    attempts        integer     NOT NULL DEFAULT 0,
    last_attempt_at timestamptz,
    delivered_at    timestamptz,
    PRIMARY KEY (trace_id, rule, channel),
    FOREIGN KEY (trace_id, rule) REFERENCES incidents (trace_id, rule)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS alert_deliveries_pending_idx
    ON alert_deliveries (last_attempt_at)
    WHERE delivered_at IS NULL;
