"""
user_jobs_tracker.py

Tracker agent: moves a job into the user_job_tracking table when the
user clicks "Add to My Jobs" in the UI.

Table: user_job_tracking
    tracking_id       SERIAL PRIMARY KEY
    user_id           INTEGER REFERENCES users(user_id)
    job_id            TEXT REFERENCES jobs(job_id)
    status            TEXT
    tailored_cv       TEXT
    status_updated_at TIMESTAMP
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  # Neon Postgres connection string


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def add_job_to_tracker(user_id: int, job_id: str, status: str = "saved", tailored_cv: str = None):
    """
    Insert a job into user_job_tracking for a given user.
    If the (user_id, job_id) pair already exists, do nothing
    (relies on the UNIQUE(user_id, job_id) constraint).

    Returns the tracking record as a dict, or None if it already existed.
    """
    query = """
        INSERT INTO user_job_tracking (
            user_id, job_id, status, tailored_cv, status_updated_at
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, job_id) DO NOTHING
        RETURNING tracking_id, user_id, job_id, status, tailored_cv, status_updated_at;
    """

    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (user_id, job_id, status, tailored_cv, now))
            row = cur.fetchone()
            conn.commit()

    if row is None:
        print(f"Job {job_id} is already tracked for user {user_id} — skipped.")
        return None

    print(f"Added job {job_id} to tracker for user {user_id} with status '{status}'.")
    return dict(row)


def update_job_status(user_id: int, job_id: str, new_status: str):
    """
    Update the status of an existing tracked job (e.g. 'saved' -> 'submitted' -> 'interview').
    """
    query = """
        UPDATE user_job_tracking
        SET status = %s, status_updated_at = %s
        WHERE user_id = %s AND job_id = %s
        RETURNING tracking_id, status, status_updated_at;
    """

    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (new_status, now, user_id, job_id))
            row = cur.fetchone()
            conn.commit()

    if row is None:
        print(f"No tracked job found for user {user_id}, job {job_id}.")
        return None

    print(f"Updated job {job_id} to status '{new_status}' for user {user_id}.")
    return dict(row)


if __name__ == "__main__":
    # Hardcoded test — simulates clicking "Add to My Jobs" in the UI
    TEST_USER_ID = 1
    TEST_JOB_ID = "dzE4cTJ2UW15NDRNekxtZEFBQUFBQT09OkVzd0JDb3dCUVVwcFZEUjBTbVY0V25wdWJXVmhXRmh5U1dOV05EazNaRVZhTTA5alR5MUlPRFZPVTNOMmRUTlFiMUZYV0Rkc1RIcFhWRU5SYjBaSFJFSmZaMjlZY25wU1NUQkJTbXBYZW1OWloyOU5Ra1ptUm10YU1VUmlSa2RhYkdsdVFWbExRM1YzVTJZdFJERlRVRXRIWkdSSGMxWTFjbUZmVTJ4cU5IVjNWakpWTWpGNGRVcFpWMFJYUlVWSFZra1NGMnMyTW5GaGNrZFhUbVpZT0RWUFZWQnJTWEpwTWxGakdpSkJSSE55T1daVGVVNTNZblZzT1hWaE9FSXRObTgxWDFScU1taGxjbTVOZEcxbg"

    add_job_to_tracker(
        user_id=TEST_USER_ID,
        job_id=TEST_JOB_ID,
        status="saved",
    )