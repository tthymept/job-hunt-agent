-- Adds a second file per tracked job: a cover letter, next to the tailored CV
-- already kept in my_upload_path. Holds the file's path in the "resumes" bucket.
-- Safe to run before the new code is deployed: it only adds a column.
-- Run once in the Supabase SQL editor.

ALTER TABLE user_job_tracking ADD COLUMN IF NOT EXISTS cover_letter_path TEXT;
