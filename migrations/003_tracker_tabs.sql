-- Splits the dashboard into tabs (e.g. "Internships 2027", "Internships 2028").
-- Every tracked job belongs to one tab. Existing jobs all go into a first tab
-- called "My jobs", which you can rename in the app.
-- Safe to run before the new code is deployed: it only adds a table and a column.
-- Run once in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS tracker_tabs (
    tab_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    -- false: the tab can still be opened and edited, but no new jobs go into it
    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    -- the tab that opens first and is pre-selected when choosing where to add a job
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Row level security on, with no policies: the anon/public API key can't read or
-- change this table. The backend uses the service key, which bypasses RLS.
ALTER TABLE tracker_tabs ENABLE ROW LEVEL SECURITY;

-- Deleting a tab leaves its untracked rows without one; the app only allows
-- deleting a tab that has no tracked jobs.
ALTER TABLE user_job_tracking
    ADD COLUMN IF NOT EXISTS tab_id BIGINT REFERENCES tracker_tabs(tab_id) ON DELETE SET NULL;

-- One first tab for every user who has none yet
INSERT INTO tracker_tabs (user_id, name, is_default)
SELECT u.user_id, 'My jobs', TRUE
FROM users u
WHERE NOT EXISTS (SELECT 1 FROM tracker_tabs t WHERE t.user_id = u.user_id);

-- Put every existing tracked job into its user's first tab
UPDATE user_job_tracking j
SET tab_id = (
    SELECT t.tab_id FROM tracker_tabs t
    WHERE t.user_id = j.user_id
    ORDER BY t.tab_id
    LIMIT 1
)
WHERE j.tab_id IS NULL;
