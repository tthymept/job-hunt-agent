"""
jobs_manager.py
------------------
Manage job_interests (saved searches) and run the daily fetch cycle:
distinct active (role, location) pairs -> search_jobs -> insert_jobs -> enrich once.
"""

import time
import psycopg2
from search_agent import search_jobs, insert_jobs, enrich_pending_jobs


def add_interest(user_id: int, role: str, country: str, city: str | None, conn) -> dict:
    """Declare a new interest. Re-activates it if it was previously removed/paused.
    Returns {'pair_is_new': bool} so caller knows whether to trigger backfill."""
    
    # Clean inputs in Python
    role_clean = role.strip().lower() if role else role
    country_clean = country.strip().lower() if country else country
    city_clean = city.strip().lower() if city else None

    cur = conn.cursor()

    # Check if pair was already backfilled
    cur.execute("""
        SELECT 1 FROM job_interests
        WHERE user_id = %s 
          AND role = %s 
          AND country = %s 
          AND city IS NOT DISTINCT FROM %s 
          AND backfilled = TRUE
        LIMIT 1
    """, (user_id, role_clean, country_clean, city_clean))
    
    pair_already_backfilled = cur.fetchone() is not None

    # Upsert relying on the named UNIQUE constraint
    cur.execute("""
        INSERT INTO job_interests (user_id, role, country, city, status, backfilled)
        VALUES (%s, %s, %s, %s, 'active', %s)
        ON CONFLICT (user_id, role, country, city)
        DO UPDATE SET status = 'active'
        RETURNING interest_id
    """, (user_id, role_clean, country_clean, city_clean, pair_already_backfilled))
    
    conn.commit()
    cur.close()

    return {"pair_is_new": not pair_already_backfilled}


def remove_interest(user_id: int, role: str, country: str, city: str | None, conn) -> None:
    role = role.strip().lower() if role else role
    country = country.strip().lower() if country else country
    city = city.strip().lower() if city else None

    cur = conn.cursor()
    cur.execute("""
        UPDATE job_interests SET status = 'removed'
        WHERE user_id = %s AND role = %s AND country = %s AND city IS NOT DISTINCT FROM %s
    """, (user_id, role, country, city))
    conn.commit()
    cur.close()


def get_distinct_active_pairs(conn) -> list[tuple[str, str, str | None]]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT role, country, city FROM job_interests WHERE status = 'active'") #'active', 'paused', 'removed'
    pairs = cur.fetchall()
    cur.close()
    return pairs


def backfill_new_pair(role: str, country: str, city: str | None, conn) -> None:
    role = role.strip().lower() if role else role
    country = country.strip().lower() if country else country
    city = city.strip().lower() if city else None

    print(f"Backfilling: {role} in {city + ', ' if city else ''}{country}")
    start = time.time()
    num_pages = 5
    date_posted = "month"

    try:
        jobs = search_jobs(role=role, country=country, city=city, num_pages=num_pages, date_posted=date_posted)
        new_count = insert_jobs(jobs, conn)
        log_fetch(conn, "backfill", role, country, city, num_pages, date_posted,
                   num_jobs_found=len(jobs), num_jobs_new=new_count,
                   duration_seconds=round(time.time() - start, 2))
    except Exception as e:
        log_fetch(conn, "backfill", role, country, city, num_pages, date_posted,
                   status="failed", error_message=str(e),
                   duration_seconds=round(time.time() - start, 2))
        raise

    cur = conn.cursor()
    cur.execute("""
        UPDATE job_interests SET backfilled = TRUE, last_fetched_at = NOW()
        WHERE role = %s AND country = %s AND city IS NOT DISTINCT FROM %s
    """, (role, country, city))
    conn.commit()
    cur.close()

    enrich_pending_jobs(conn)


def run_daily_fetch(conn) -> None:
    pairs = get_distinct_active_pairs(conn)
    print(f"Fetching daily jobs for {len(pairs)} distinct interest pair(s)")

    for role, country, city in pairs:
        start = time.time()
        try:
            jobs = search_jobs(role=role, country=country, city=city, num_pages=1, date_posted="today")
            new_count = insert_jobs(jobs, conn)
            log_fetch(conn, "daily_search", role, country, city, num_pages=1, date_posted="today",
                       num_jobs_found=len(jobs), num_jobs_new=new_count,
                       duration_seconds=round(time.time() - start, 2))
        except Exception as e:
            log_fetch(conn, "daily_search", role, country, city, num_pages=1, date_posted="today",
                       status="failed", error_message=str(e),
                       duration_seconds=round(time.time() - start, 2))
            continue

        cur = conn.cursor()
        cur.execute("""
            UPDATE job_interests SET last_fetched_at = NOW()
            WHERE role = %s AND country = %s AND city IS NOT DISTINCT FROM %s
        """, (role, country, city))
        conn.commit()
        cur.close()

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM jobs WHERE enrichment_status IN ('pending', 'failed') AND enrichment_attempts < 5")
    pending_count = cur.fetchone()[0]
    cur.close()

    expected_calls = -(-pending_count // 10)
    start = time.time()
    enrich_pending_jobs(conn)
    log_fetch(conn, "enrichment", num_jobs_found=pending_count,
               num_gemini_calls=expected_calls,
               duration_seconds=round(time.time() - start, 2))


def log_fetch(conn, run_type, role=None, country=None, city=None, num_pages=None,
              date_posted=None, num_jobs_found=None, num_jobs_new=None,
              num_gemini_calls=None, status="success", error_message=None,
              duration_seconds=None):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO fetch_logs (
            run_type, role, country, city, num_pages, date_posted,
            num_jobs_found, num_jobs_new, num_gemini_calls,
            status, error_message, duration_seconds
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (run_type, role, country, city, num_pages, date_posted,
          num_jobs_found, num_jobs_new, num_gemini_calls,
          status, error_message, duration_seconds))
    conn.commit()
    cur.close()


if __name__ == "__main__":
    import os
    DATABASE_URL = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(DATABASE_URL)
    ROLE = "Data Engineer intern"# OR "Machine Learning Engineer intern" OR "AI Infrastructure intern" OR "Data Engineer intern")'
    #ROLE = "data science intern"
    COUNTRY = "Singapore"
    CITY = None # Singapore = None

    result = add_interest(user_id=1, role=ROLE, country=COUNTRY, city=CITY, conn=conn)
    if result["pair_is_new"]:
        backfill_new_pair(ROLE, COUNTRY, CITY, conn)

    #run_daily_fetch(conn)

    conn.close()