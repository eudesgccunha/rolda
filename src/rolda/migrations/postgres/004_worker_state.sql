-- Worker progress. One row per worker name, so a restarted or replaced worker
-- resumes where the last one stopped instead of at "now minus the window".
CREATE TABLE IF NOT EXISTS worker_state (
    name       text        PRIMARY KEY,
    cursor     timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
