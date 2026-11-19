"""
search_agent.py
----------------
Search jobs via JSearch -> insert raw rows into Postgres (pending)
-> enrich pending rows with LLM-extracted fields, batched N-per-call -> update rows.

Setup:
    uv add requests python-dotenv psycopg2-binary google-genai
"""

import os
import re
import json
import time
import requests
import psycopg2
import pycountry
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

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

BATCH_SIZE = 25             # most jobs per Gemini call
BATCH_MAX_CHARS = 60_000    # and at most this much description text per call
MAX_DESCRIPTION_CHARS = 12_000  # longer descriptions are cut (the details sit near the start)


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
            "language": "en",
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

    print(f"Found {len(all_jobs)} jobs")
    return all_jobs


# ---------- STEP 1b: keep only jobs worth storing ----------
# Everything stored is read by Gemini (step 3), so jobs are filtered and
# de-duplicated here first: nothing skipped here costs a Gemini call.

INTERNSHIP_TITLE = re.compile(
    r"\b(interns?|internships?|trainees?|placements?|co-?op|industrial attachment|working student)\b", re.I
)

# Publishers seen in results that aren't job boards at all (blogs, Q&A sites)
JUNK_PUBLISHER_HINTS = ("blogspot.", ".kro.kr", "questions and answers", "prepterview")

# Sites that mostly repost other boards' jobs, often behind their own sign-up page
REPOSTER_HINTS = (
    "trabajo.org", "jobleads", "expertini", "bebee", "learn4good", "jooble",
    "talent.com", "jobiglo", "workvale", "ai search", "ai-search",
)

# Words that don't tell two companies apart ("Micron Technology, Inc." -> "micron")
GENERIC_COMPANY_WORDS = {
    "the", "pte", "ltd", "limited", "inc", "co", "corp", "corporation", "llc", "plc", "sdn", "bhd",
    "group", "holdings", "international", "singapore", "sg", "asia", "pacific", "apac", "company",
}


def wants_internships(role: str) -> bool:
    """An interest like "data engineer intern" only wants internships."""
    return "intern" in (role or "").lower()


def is_internship(job: dict) -> bool:
    return bool(INTERNSHIP_TITLE.search(job.get("job_title") or ""))


def is_junk_publisher(job: dict) -> bool:
    publisher = (job.get("job_publisher") or "").lower()
    return any(hint in publisher for hint in JUNK_PUBLISHER_HINTS)


def _words(text: str | None) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()


def dedupe_key(job: dict) -> tuple[str, str]:
    """The same job listed on several sites shares its company and title, so
    (main company word, normalised title) identifies it across sites."""
    company = [w for w in _words(job.get("employer_name")) if w not in GENERIC_COMPANY_WORDS]
    return (company[0] if company else "", " ".join(_words(job.get("job_title"))))


def source_rank(job: dict) -> int:
    """Which copy of a job to keep, lower is better: the company's own careers
    page, then LinkedIn, then other boards, then sites that repost others' jobs."""
    publisher = (job.get("job_publisher") or "").lower()
    company = dedupe_key(job)[0]
    if any(hint in publisher for hint in REPOSTER_HINTS):
        return 3
    # The company's own site: its name in the publisher ("SAP Careers"), or a careers
    # system ("Careers At Micron Technology", Workday). Not boards that merely
    # contain the word, like MyCareersFuture.
    if (company and company in publisher) or publisher.startswith("careers at") or "workday" in publisher:
        return 0
    if "linkedin" in publisher:
        return 1
    return 2


def select_jobs(jobs: list[dict], role: str, stored: dict[tuple, dict]) -> tuple[list[dict], list[tuple[dict, dict]], Counter]:
    """Decides what to do with a search's results, given the jobs already stored
    ({dedupe_key: {job_id, job_publisher, ...}}). Returns
    (jobs to insert, [(stored job, better copy)] whose link to swap in, reasons for skipping)."""
    skipped = Counter()
    best: dict[tuple, dict] = {}
    for job in jobs:
        if is_junk_publisher(job):
            skipped["not a job site"] += 1
        elif wants_internships(role) and not is_internship(job):
            skipped["not an internship"] += 1
        else:
            key = dedupe_key(job)
            if key in best:
                skipped["same job from another site"] += 1
                if source_rank(job) < source_rank(best[key]):
                    best[key] = job
            else:
                best[key] = job

    to_insert, upgrades = [], []
    for key, job in best.items():
        existing = stored.get(key)
        if existing is None:
            to_insert.append(job)
        elif source_rank(job) < source_rank(existing) and job.get("job_apply_link") != existing.get("job_apply_link"):
            upgrades.append((existing, job))
            skipped["already stored (better link swapped in)"] += 1
        else:
            skipped["already stored"] += 1
    return to_insert, upgrades, skipped


def load_stored_keys(conn) -> dict[tuple, dict]:
    cur = conn.cursor()
    cur.execute("SELECT job_id, employer_name, job_title, job_publisher, job_apply_link FROM jobs")
    stored = {}
    for job_id, employer, title, publisher, link in cur.fetchall():
        row = {"job_id": job_id, "employer_name": employer, "job_title": title,
               "job_publisher": publisher, "job_apply_link": link}
        stored.setdefault(dedupe_key(row), row)
    cur.close()
    return stored


def store_jobs(jobs: list[dict], role: str, conn) -> int:
    """Filters and de-duplicates a search's results, inserts the new ones (to be
    read by Gemini later) and swaps better links into stored copies. Returns how
    many new jobs were stored."""
    to_insert, upgrades, skipped = select_jobs(jobs, role, load_stored_keys(conn))
    cur = conn.cursor()
    for existing, better in upgrades:
        # Same job_id, so anything tracking it keeps working; skipped if another row already has that link
        cur.execute("""
            UPDATE jobs SET job_apply_link = %s, job_publisher = %s
            WHERE job_id = %s AND NOT EXISTS (SELECT 1 FROM jobs WHERE job_apply_link = %s)
        """, (better.get("job_apply_link"), better.get("job_publisher"), existing["job_id"], better.get("job_apply_link")))
    conn.commit()
    cur.close()
    new_count = insert_jobs(to_insert, conn)
    print(f"Kept {len(to_insert)} of {len(jobs)} ({new_count} new); skipped: {dict(skipped)}")
    return new_count


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

def batches(rows: list[tuple[str, str]], max_jobs: int = BATCH_SIZE, max_chars: int = BATCH_MAX_CHARS):
    """Groups (job_id, description) rows into as few Gemini calls as fit: up to
    max_jobs per call, and no more than max_chars of description text."""
    batch, size = [], 0
    for job_id, description in rows:
        length = len(description or "")
        if batch and (len(batch) == max_jobs or size + length > max_chars):
            yield batch
            batch, size = [], 0
        batch.append((job_id, description))
        size += length
    if batch:
        yield batch


def extract_job_info_batch(jobs: list[tuple[str, str]]) -> dict[str, dict]:
    """
    jobs: list of (job_id, description) tuples.
    Returns {job_id: extracted_dict} for every job the model successfully returned.
    """
    # Each posting is sent with a short number, not its job_id: JSearch ids are
    # ~400 characters and the model sometimes copied one back wrong, losing that job
    postings = [{"ref": str(n), "description": (desc or "")[:MAX_DESCRIPTION_CHARS]} for n, (_, desc) in enumerate(jobs, 1)]
    job_ids = {str(n): jid for n, (jid, _) in enumerate(jobs, 1)}

    prompt = f"""Extract structured info for EACH job posting below. Return ONLY a JSON array
(no markdown, no other text), one object per posting, in this exact shape:

[
  {{
    "ref": "must match the input ref exactly",
    "duration": "string or null - human-readable internship length/dates if mentioned",
    "min_duration_months": "integer or null - convert duration to number of months (e.g. '12-week' -> 3)",
    "skills": ["array of specific tools/skills mentioned"],
    "application_deadline": "string or null - explicit deadline if stated"
  }}
]

Postings:
{json.dumps(postings, indent=2)}
"""

    # JSON mode: the reply is always parseable, so a batch isn't lost (and retried) over formatting
    response = gemini_client.models.generate_content(
        model="gemini-3.5-flash-lite", #"gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    results = json.loads(text)  # expects a list

    return {job_ids[str(r["ref"])]: r for r in results if str(r.get("ref")) in job_ids}


# ---------- STEP 4: enrich pending rows, processed in batches ----------

def enrich_pending_jobs(conn, batch_size: int = BATCH_SIZE) -> int:
    """Reads duration, skills and deadline for every job not read yet. Returns the number of Gemini calls made."""
    cur = conn.cursor()
    cur.execute("""
        SELECT job_id, job_description FROM jobs
        WHERE enrichment_status IN ('pending', 'failed') AND enrichment_attempts < 5
    """)
    rows = cur.fetchall()

    # Nothing to read in an empty description: mark it done without a Gemini call
    empty = [jid for jid, desc in rows if not (desc or "").strip()]
    if empty:
        cur.execute("UPDATE jobs SET enrichment_status='done' WHERE job_id = ANY(%s)", (empty,))
        conn.commit()
    rows = [(jid, desc) for jid, desc in rows if (desc or "").strip()]

    planned = list(batches(rows, max_jobs=batch_size))
    print(f"Enriching {len(rows)} job(s) in {len(planned)} Gemini call(s)"
          f"{f'; {len(empty)} with no description skipped' if empty else ''}")

    for batch in planned:
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
                    application_deadline=%s,
                    enrichment_status='done'
                WHERE job_id=%s
            """, (
                extracted.get("duration"), extracted.get("min_duration_months"),
                extracted.get("skills"), extracted.get("application_deadline"),
                job_id,
            ))

        conn.commit()
        time.sleep(13)  # still respect per-minute rate limit between batches

    cur.close()
    return len(planned)


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