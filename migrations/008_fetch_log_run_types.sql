-- Allows the fetch log's newer run types:
--   cleanup              the stale-job cleanup at the end of each scheduled run
--                        (it was never allowed, so that log line failed)
--   theirstack           the scheduled TheirStack fetch (Thailand)
--   theirstack_backfill  a new Thailand interest's first fetch
--   theirstack_test      credits spent testing TheirStack by hand
-- For TheirStack rows, num_jobs_found is the credits spent (one per job returned).
-- Run once in the Supabase SQL editor.

ALTER TABLE fetch_logs DROP CONSTRAINT IF EXISTS fetch_logs_run_type_check;
ALTER TABLE fetch_logs ADD CONSTRAINT fetch_logs_run_type_check CHECK (run_type IN (
    'backfill', 'daily_search', 'enrichment', 'cleanup',
    'theirstack', 'theirstack_backfill', 'theirstack_test'
));
