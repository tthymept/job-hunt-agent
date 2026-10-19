-- The app writes 'Saved / Not Applied' as the first status, but the column
-- default was 'not_applied'. Align the default with what the app uses and
-- fix any rows that picked up the old default.
-- Run once in the Supabase SQL editor.

ALTER TABLE user_job_tracking ALTER COLUMN status SET DEFAULT 'Saved / Not Applied';

UPDATE user_job_tracking SET status = 'Saved / Not Applied' WHERE status = 'not_applied';
