-- Status history: one row for every stage a tracked job reaches, with the day it
-- happened. The day can be edited, because the status is often updated days
-- after the email arrived. It replaces submitted_at, which the app no longer
-- reads (the Submitted row holds that date now).
-- Each stage can also hold a scheduled time (OA due date, interview date and
-- time, offer reply-by date), whether it is done, and a note.
-- Also adds free-text notes and a contact (e.g. the recruiter) to each job.
-- Run this before deploying the code that reads it.
-- Run once in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS status_events (
    event_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tracking_id  INTEGER NOT NULL REFERENCES user_job_tracking(tracking_id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status       TEXT NOT NULL,
    -- when the job reached this stage (edits are stored at noon UTC, so the day
    -- is the same in every time zone)
    happened_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- OA due date, interview date and time, or offer reply-by date
    scheduled_at TIMESTAMPTZ,
    done         BOOLEAN NOT NULL DEFAULT FALSE,
    done_at      TIMESTAMPTZ,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- the history is the path to the current stage: each stage at most once
    UNIQUE (tracking_id, status)
);

-- Row level security on, with no policies: only the backend (service key) can use it
ALTER TABLE status_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE user_job_tracking ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE user_job_tracking ADD COLUMN IF NOT EXISTS contact TEXT;

-- Starting history for jobs tracked before this existed.
-- 1. A Submitted row for every job with a submitted date
INSERT INTO status_events (tracking_id, user_id, status, happened_at)
SELECT j.tracking_id, j.user_id, 'Submitted', j.submitted_at
FROM user_job_tracking j
WHERE j.submitted_at IS NOT NULL
  AND j.status NOT IN ('Saved / Not Applied', 'Untracked')
ON CONFLICT (tracking_id, status) DO NOTHING;

-- 2. A row for the current stage of every job past Submitted, dated when its
--    status last changed (the only date there is for it)
INSERT INTO status_events (tracking_id, user_id, status, happened_at)
SELECT j.tracking_id, j.user_id, j.status, COALESCE(j.status_updated_at, now())
FROM user_job_tracking j
WHERE j.status IN ('Online Assignment', 'Interview Round 1', 'Interview Round 2', 'Offered', 'Rejected')
ON CONFLICT (tracking_id, status) DO NOTHING;
