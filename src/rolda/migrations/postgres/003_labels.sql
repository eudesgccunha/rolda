-- Rolda M5: labels. One label per incident and source (human or judge),
-- so human and judge verdicts can be compared later.
CREATE TABLE IF NOT EXISTS labels (
    trace_id   text        NOT NULL,
    rule       text        NOT NULL,
    source     text        NOT NULL CHECK (source IN ('human', 'judge')),
    verdict    text        NOT NULL
               CHECK (verdict IN ('failure', 'false_alarm', 'uncertain')),
    reason     text        NOT NULL DEFAULT '',
    labeler    text        NOT NULL,
    labeled_at timestamptz NOT NULL,
    PRIMARY KEY (trace_id, rule, source),
    FOREIGN KEY (trace_id, rule) REFERENCES incidents (trace_id, rule)
);
