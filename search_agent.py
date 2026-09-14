"""
search_agent.py
----------------
Search jobs via JSearch -> insert raw rows into Postgres (pending)
-> enrich pending rows with LLM-extracted fields -> update rows.

Setup:
    uv add requests python-dotenv psycopg2-binary google-genai
"""

import os
import json
import time
import requests
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from google import genai

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"
HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# ---------- STEP 1: search ----------

def search_jobs(role: str, location: str, num_pages: int = 1, remote_only: bool = False) -> list[dict]:
    query = f"{role} in {location}"
    params = {
        "query": query,
        "page": "1",
        "num_pages": str(num_pages),
        "date_posted": "month", # month, week, today
    }
    if remote_only:
        params["remote_jobs_only"] = "true"

    response = requests.get(JSEARCH_URL, headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("data", {}).get("jobs", [])


# ---------- STEP 2: insert raw rows (pending) ----------

def insert_jobs(jobs: list[dict], conn) -> None:
    cur = conn.cursor()
    for job in jobs:
        cur.execute("""
            INSERT INTO jobs (
                job_id, job_title, employer_name, job_publisher,
                job_employment_type, job_apply_link, job_description,
                job_is_remote, job_city, job_country,
                job_posted_at_datetime_utc, job_offer_expiration_datetime_utc,
                job_normalized_title
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (job_apply_link) DO NOTHING
        """, (
            job.get("job_id"), job.get("job_title"), job.get("employer_name"),
            job.get("job_publisher"), job.get("job_employment_type"),
            job.get("job_apply_link"), job.get("job_description"),
            job.get("job_is_remote"), job.get("job_city"), job.get("job_country"),
            job.get("job_posted_at_datetime_utc"), job.get("job_offer_expiration_datetime_utc"),
            job.get("job_normalized_title"),
        ))
    conn.commit()
    cur.close()


# ---------- STEP 3: extract missing info via LLM ----------

def extract_job_info(description: str) -> dict:
    prompt = f"""Extract the following from this internship posting. Return ONLY valid JSON, no markdown, no other text:
{{
  "duration": "string or null - human-readable internship length/dates if mentioned",
  "min_duration_months": "integer or null - convert duration to number of months (e.g. '12-week' -> 3)",
  "skills": ["array of specific tools/skills mentioned"],
  "application_deadline": "string or null - explicit deadline if stated",
  "short_description": "one sentence summary"
}}

Posting:
{description}
"""
    response = gemini_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
    )
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)


# ---------- STEP 4: enrich pending rows ----------

def enrich_pending_jobs(conn) -> None:
    cur = conn.cursor()
    cur.execute("""
        SELECT job_id, job_description FROM jobs
        WHERE enrichment_status IN ('pending', 'failed') AND enrichment_attempts < 3
    """)
    rows = cur.fetchall()

    for job_id, description in rows:
        try:
            extracted = extract_job_info(description or "")
            cur.execute("""
                UPDATE jobs
                SET duration=%s, min_duration_months=%s, skills=%s,
                    application_deadline=%s, short_description=%s,
                    enrichment_status='done'
                WHERE job_id=%s
            """, (
                extracted.get("duration"), extracted.get("min_duration_months"),
                extracted.get("skills"), extracted.get("application_deadline"),
                extracted.get("short_description"), job_id,
            ))
            conn.commit()
        except Exception as e:
            print(f"Failed to enrich {job_id}: {e}")
            cur.execute("""
                UPDATE jobs
                SET enrichment_status='failed', enrichment_attempts = enrichment_attempts + 1
                WHERE job_id=%s
            """, (job_id,))
            conn.commit()

        time.sleep(13)

    cur.close()

# ---------- Debugging function(s) ----------

def print_job_summary(jobs: list[dict]) -> None:
    print(f"\nFound {len(jobs)} postings:\n")
    for job in jobs:
        title = job.get("job_title", "Unknown title")
        company = job.get("employer_name", "Unknown company")
        source = job.get("job_publisher", "Unknown source")   # e.g. "LinkedIn", "Indeed"
        link = job.get("job_apply_link", "")
        posted = job.get("job_posted_at", "Unknown date")
 
        print(f"- {title} @ {company}")
        print(f"  Source: {source}  |  Posted: {posted}")
        print(f"  Apply: {link}\n")


if __name__ == "__main__":
    ROLE = "data scientist intern"
    LOCATION = "Singapore"

    jobs = search_jobs(role=ROLE, location=LOCATION, num_pages=6)
    print(f"Found {len(jobs)} postings")

    conn = psycopg2.connect(DATABASE_URL)
    insert_jobs(jobs, conn)
    enrich_pending_jobs(conn)
    conn.close()
    print("Done.")