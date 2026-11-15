-- One user can't have two tabs with the same name (upper and lower case count
-- as the same). The app already refuses this; the index makes the database
-- refuse it too, even if two requests arrive at the same moment.
-- If this fails with "could not create unique index", two tabs still share a
-- name: rename or delete one in the app, then run it again.
-- Run once in the Supabase SQL editor.

CREATE UNIQUE INDEX IF NOT EXISTS tracker_tabs_user_name_unique
    ON tracker_tabs (user_id, lower(name));
