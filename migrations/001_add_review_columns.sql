-- Adds the review-stage columns to tables that were created before they existed.
-- Base.metadata.create_all() only creates missing TABLES, it never adds columns
-- to existing ones, so run this once against an existing database:
--
--   psql postgresql://backtest:backtest@localhost:5432/backtest -f migrations/001_add_review_columns.sql
--
-- Safe to run more than once. Not needed for a fresh database.

ALTER TABLE backtest_days
    ADD COLUMN IF NOT EXISTS review_verdict    VARCHAR(20),
    ADD COLUMN IF NOT EXISTS review_confidence DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS review_reason     TEXT,
    ADD COLUMN IF NOT EXISTS recheck_rounds    INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS approved_action   VARCHAR(10);

ALTER TABLE backtest_agent_responses
    ADD COLUMN IF NOT EXISTS review_round INTEGER;
