-- Rolda M4: probable cause. The signature groups similar incidents
-- (agent|rule|operation|normalized error). The path lists span names from
-- the trace root to the span behind the finding.
ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS signature text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS path text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS incidents_signature_idx
    ON incidents (signature);
