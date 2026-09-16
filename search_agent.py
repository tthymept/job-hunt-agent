"""
search_agent.py
----------------
Search jobs via JSearch -> insert raw rows into Postgres (pending)
-> enrich pending rows with LLM-extracted fields, batched N-per-call -> update rows.

Setup:
    uv add requests python-dotenv psycopg2-binary google-genai
"""

import os
import json
import time
import requests
import psycopg2
import pycountry
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

BATCH_SIZE = 10  # jobs per Gemini call -- tune down if descriptions are long / hitting token limits


def get_country_code(country_name: str) -> str | None:
    try:
        return pycountry.countries.lookup(country_name).alpha_2.lower()
    except LookupError:
        return None

#get_country_code("United States")  # -> "us"
#get_country_code("Thailand")       # -> "th"


def build_location_text(country: str, city: str | None) -> str:
    if not city or city.strip().lower() == country.strip().lower():
        return country
    return f"{city}, {country}"

# ---------- STEP 1: search ----------

def search_jobs(role: str, country: str, city: str | None = None, num_pages: int = 3,
                 date_posted: str = "today") -> list[dict]:
    country_code = get_country_code(country)
    location_text = build_location_text(country, city)
    query = f"{role} in {location_text}"

    all_jobs = []
    cursor = None

    for _ in range(num_pages):
        params = {
            "query": query,
            "date_posted": date_posted,
            "country": country_code,
            "employment_types": "INTERN",
        }
        if cursor:
            params["cursor"] = cursor

        response = requests.get(JSEARCH_URL, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()

        result = data.get("data", {})
        jobs = result.get("jobs", [])
        cursor = result.get("cursor")

        if not jobs:
            break
        all_jobs.extend(jobs)
        if not cursor:
            break

    internship_jobs = [j for j in all_jobs if is_internship(j)]
    print(f"Filtered {len(all_jobs)} -> {len(internship_jobs)} internships")
    return internship_jobs


def is_internship(job: dict) -> bool:
    text = f"{job.get('job_title', '')} {job.get('job_employment_type', '')}".lower()
    return "intern" in text


# ---------- STEP 2: insert raw rows (pending) ----------

def insert_jobs(jobs: list[dict], conn) -> int:
    cur = conn.cursor()
    new_count = 0
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
        if cur.rowcount > 0:
            new_count += 1
    conn.commit()
    cur.close()
    return new_count


# ---------- STEP 3: extract missing info via LLM (batched -- N jobs per call) ----------

def chunked(rows: list, size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def extract_job_info_batch(jobs: list[tuple[str, str]]) -> dict[str, dict]:
    """
    jobs: list of (job_id, description) tuples.
    Returns {job_id: extracted_dict} for every job the model successfully returned.
    """
    postings = [{"job_id": jid, "description": desc or ""} for jid, desc in jobs]

    prompt = f"""Extract structured info for EACH job posting below. Return ONLY a JSON array
(no markdown, no other text), one object per posting, in this exact shape:

[
  {{
    "job_id": "must match the input job_id exactly",
    "duration": "string or null - human-readable internship length/dates if mentioned",
    "min_duration_months": "integer or null - convert duration to number of months (e.g. '12-week' -> 3)",
    "skills": ["array of specific tools/skills mentioned"],
    "application_deadline": "string or null - explicit deadline if stated",
    "short_description": "one sentence summary"
  }}
]

Postings:
{json.dumps(postings, indent=2)}
"""

    response = gemini_client.models.generate_content(
        model="gemini-3.5-flash-lite", #"gemini-3.6-flash",
        contents=prompt,
    )
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    results = json.loads(text)  # expects a list

    return {r["job_id"]: r for r in results if "job_id" in r}


# ---------- STEP 4: enrich pending rows, processed in batches ----------

def enrich_pending_jobs(conn, batch_size: int = BATCH_SIZE) -> None:
    cur = conn.cursor()
    cur.execute("""
        SELECT job_id, job_description FROM jobs
        WHERE enrichment_status IN ('pending', 'failed') AND enrichment_attempts < 5
    """)
    rows = cur.fetchall()
    print(f"Enriching {len(rows)} job(s) in batches of {batch_size} "
          f"({-(-len(rows) // batch_size)} Gemini call(s) total)")

    for batch in chunked(rows, batch_size):
        job_ids_in_batch = [jid for jid, _ in batch]

        try:
            results = extract_job_info_batch(batch)
        except Exception as e:
            # whole batch failed (bad JSON, API error, etc.) -- mark all as failed, retry later
            print(f"Batch failed entirely {job_ids_in_batch}: {e}")
            cur.execute("""
                UPDATE jobs
                SET enrichment_status='failed', enrichment_attempts = enrichment_attempts + 1
                WHERE job_id = ANY(%s)
            """, (job_ids_in_batch,))
            conn.commit()
            time.sleep(13)
            continue

        for job_id in job_ids_in_batch:
            extracted = results.get(job_id)
            if extracted is None:
                # model returned the batch but skipped/mismatched this specific job_id
                print(f"No result returned for {job_id}, marking failed")
                cur.execute("""
                    UPDATE jobs
                    SET enrichment_status='failed', enrichment_attempts = enrichment_attempts + 1
                    WHERE job_id=%s
                """, (job_id,))
                continue

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
        time.sleep(13)  # still respect per-minute rate limit between batches

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
    COUNTRY = "Singapore"

    jobs = search_jobs(role=ROLE, country=COUNTRY, num_pages=2)
    print(f"Found {len(jobs)} postings")

    conn = psycopg2.connect(DATABASE_URL)
    insert_jobs(jobs, conn)
    enrich_pending_jobs(conn)
    conn.close()
    print("Done.")