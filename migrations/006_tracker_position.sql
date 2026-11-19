-- Adds "My order": where each tracked job sits in its tab, set with the up and
-- down arrows on the dashboard (1 = top). Existing jobs keep the order they
-- were added in, which is how the dashboard listed them until now.
-- Run this before deploying the code that reads it.
-- Run once in the Supabase SQL editor.

ALTER TABLE user_job_tracking ADD COLUMN IF NOT EXISTS position INTEGER;

UPDATE user_job_tracking j
SET position = numbered.n
FROM (
    SELECT tracking_id,
           ROW_NUMBER() OVER (PARTITION BY user_id, tab_id ORDER BY tracking_id) AS n
    FROM user_job_tracking
) AS numbered
WHERE j.tracking_id = numbered.tracking_id
  AND j.position IS NULL;
