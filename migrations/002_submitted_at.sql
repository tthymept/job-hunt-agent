-- Adds the date a job was marked Submitted, shown on the dashboard.
-- Jobs already at Submitted start with the date their status last changed.
-- Jobs already past Submitted stay empty: their last change was a later stage.
-- Run once in the Supabase SQL editor.

ALTER TABLE user_job_tracking ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;

UPDATE user_job_tracking SET submitted_at = status_updated_at
WHERE status = 'Submitted' AND submitted_at IS NULL;
