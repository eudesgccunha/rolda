-- The agent name moves out of the signature into a column of its own, so the
-- API can filter and page by agent with an index instead of scanning every
-- incident. Existing rows are filled from the signature.
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS agent text NOT NULL DEFAULT '';

UPDATE incidents SET agent = split_part(signature, '|', 1) WHERE agent = '';

CREATE INDEX IF NOT EXISTS incidents_agent_idx
    ON incidents (agent, detected_at DESC, trace_id DESC, rule DESC);

CREATE INDEX IF NOT EXISTS incidents_detected_idx
    ON incidents (detected_at DESC, trace_id DESC, rule DESC);
