-- Migration for an EXISTING `run` table (deployments created before the web/worker
-- split). Fresh installs get these from cleanroom/db/schema.sql; this brings older
-- databases up to date. Idempotent. Apply as admin:
--
--     psql "$CLEANROOM_PG_DSN" -f sql/run_queue.sql

ALTER TABLE run ADD COLUMN IF NOT EXISTS iterations_target integer NOT NULL DEFAULT 0;

-- Keeps the worker's claim query (FOR UPDATE SKIP LOCKED over queued rows) cheap.
CREATE INDEX IF NOT EXISTS run_queued_idx ON run (run_id) WHERE state = 'queued';
