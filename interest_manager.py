"""
interest_manager.py
------------------
Manage job_interests (saved searches) and run the daily fetch cycle:
distinct active (role, location) pairs -> search_jobs -> insert_jobs -> enrich once.
"""

import psycopg2
from search_agent import search_jobs, insert_jobs, enrich_pending_jobs


def add_interest(user_id: int, role: str, location: str, conn) -> dict:
    """Declare a new interest. Re-activates it if it was previously removed/paused.
    Returns {'pair_is_new': bool} so caller knows whether to trigger backfill."""
    cur = conn.cursor()

    # is this (role, location) pair brand new across ALL users, or already backfilled by someone?
    cur.execute("""
        SELECT 1 FROM job_interests
        WHERE role = %s AND location = %s AND backfilled = TRUE
        LIMIT 1
    """, (role, location))
    pair_already_backfilled = cur.fetchone() is not None

    cur.execute("""
        INSERT INTO job_interests (user_id, role, location, status, backfilled)
        VALUES (%s, %s, %s, 'active', %s)
        ON CONFLICT (user_id, role, location)
        DO UPDATE SET status = 'active'
        RETURNING interest_id
    """, (user_id, role, location, pair_already_backfilled))
    conn.commit()
    cur.close()

    return {"pair_is_new": not pair_already_backfilled}


def remove_interest(user_id: int, role: str, location: str, conn) -> None:
    cur = conn.cursor()
    cur.execute("""
        UPDATE job_interests SET status = 'removed'
        WHERE user_id = %s AND role = %s AND location = %s
    """, (user_id, role, location))
    conn.commit()
    cur.close()


def get_distinct_active_pairs(conn) -> list[tuple[str, str]]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT role, location FROM job_interests WHERE status = 'active'")
    pairs = cur.fetchall()
    cur.close()
    return pairs


def backfill_new_pair(role: str, location: str, conn) -> None:
    """One-time last-month pull for a pair nobody has fetched before."""
    print(f"Backfilling: {role} in {location}")
    jobs = search_jobs(role=role, location=location, num_pages=5, date_posted="month")
    insert_jobs(jobs, conn)

    cur = conn.cursor()
    cur.execute("""
        UPDATE job_interests SET backfilled = TRUE, last_fetched_at = NOW()
        WHERE role = %s AND location = %s
    """, (role, location))
    conn.commit()
    cur.close()


def run_daily_fetch(conn) -> None:
    """Run once a day: fetch today's postings for every distinct active pair,
    then enrich everything pending in ONE pass (max batching, min Gemini calls)."""
    pairs = get_distinct_active_pairs(conn)
    print(f"Fetching daily jobs for {len(pairs)} distinct interest pair(s)")

    for role, location in pairs:
        jobs = search_jobs(role=role, location=location, num_pages=1, date_posted="today")
        insert_jobs(jobs, conn)

        cur = conn.cursor()
        cur.execute("""
            UPDATE job_interests SET last_fetched_at = NOW()
            WHERE role = %s AND location = %s
        """, (role, location))
        conn.commit()
        cur.close()

    enrich_pending_jobs(conn)  # one batched pass across all newly inserted jobs


if __name__ == "__main__":
    import os
    DATABASE_URL = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(DATABASE_URL)

    # example: declaring a new interest (call this from your "Feed job into website" UI action)
    result = add_interest(user_id=1, role="data scientist intern", location="Singapore", conn=conn)
    if result["pair_is_new"]:
        backfill_new_pair("data scientist intern", "Singapore", conn)

    # example: the daily cron entrypoint
    run_daily_fetch(conn)

    conn.close()