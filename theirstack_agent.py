"""
theirstack_agent.py
--------------------
Job search for countries JSearch doesn't cover (Thailand returns nothing there),
through TheirStack's job search API. It collects from LinkedIn, JobsDB/SEEK,
company career sites and more.

TheirStack charges 1 API credit for every job it returns, so:
  - all of a country's interests go out as ONE request (a job matching two
    interests is paid for once),
  - each scheduled run only asks for jobs discovered since the previous run,
    and never for jobs already stored,
  - every run stays inside THEIRSTACK_BUDGET credits per 30 days, below the
    free plan's 200. Without a card on the account nothing can be charged; the
    budget also stops the free credits running out mid-month.
Credits spent are kept in fetch_logs (num_jobs_found of the theirstack runs).
"""

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

THEIRSTACK_URL = "https://api.theirstack.com/v1/jobs/search"
THEIRSTACK_BUDGET = 180  # credits per 30 days; the free plan has 200
PAGE_SIZE = 25           # the most jobs per page on the free plan
MAX_AGE_DAYS = 30        # only jobs posted in the last month

# Interests in these countries are searched here instead of JSearch
THEIRSTACK_COUNTRIES = {"thailand"}

# Log types that spend credits; the budget counts all of them
CREDIT_RUN_TYPES = ("theirstack", "theirstack_backfill", "theirstack_test")

# Readable names for the sites jobs come from
SOURCE_NAMES = {
    "linkedin.com": "LinkedIn",
    "seek.com": "JobsDB (SEEK)",
    "jobsdb.com": "JobsDB",
    "jobthai.com": "JobThai",
    "indeed.com": "Indeed",
    "glassdoor.com": "Glassdoor",
}


def uses_theirstack(country: str) -> bool:
    return (country or "").strip().lower() in THEIRSTACK_COUNTRIES


def title_patterns(roles: list[str]) -> list[str]:
    """TheirStack title patterns for a set of interests. A title matches a
    pattern when it contains all of its words, so "data science intern" would
    miss "Data Science Internship": an "internship" form is added for each.
    Commas aren't allowed, and quoted "a" or "b" interests become separate patterns."""
    patterns = []
    for role in roles:
        for part in re.split(r"\s+or\s+", role or "", flags=re.I):
            words = re.sub(r"[^\w\s&+.#-]", " ", part).split()
            if not words:
                continue
            pattern = " ".join(words).lower()
            patterns.append(pattern)
            if re.search(r"\bintern\b", pattern):
                patterns.append(re.sub(r"\bintern\b", "internship", pattern))
    return list(dict.fromkeys(patterns))


def source_name(url: str | None) -> str:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    for domain, name in SOURCE_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host or "TheirStack"


def to_job_row(job: dict) -> dict:
    """A TheirStack job in the shape search_agent.store_jobs expects (JSearch's field names)."""
    link = job.get("final_url") or job.get("url") or job.get("source_url")
    city = next((loc.get("name") for loc in job.get("locations") or [] if loc.get("type") == "city"), None)
    return {
        "job_id": f"ts-{job['id']}",
        "job_title": job.get("job_title"),
        "employer_name": job.get("company") or (job.get("company_object") or {}).get("name"),
        "job_publisher": source_name(job.get("source_url") or job.get("url")),
        "job_employment_type": ", ".join(job.get("employment_statuses") or []) or None,
        "job_apply_link": link,
        "job_description": job.get("description"),
        "job_is_remote": job.get("remote"),
        "job_city": city or job.get("short_location"),
        "job_country": job.get("country_code"),
        "job_posted_at_datetime_utc": job.get("date_posted"),
        "job_offer_expiration_datetime_utc": job.get("closed_at"),
        "job_normalized_title": job.get("normalized_title") or None,
    }


def credits_used(conn, days: int = 30) -> int:
    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(SUM(num_jobs_found), 0) FROM fetch_logs
        WHERE run_type = ANY(%s) AND run_at > NOW() - make_interval(days => %s)
    """, (list(CREDIT_RUN_TYPES), days))
    used = cur.fetchone()[0]
    cur.close()
    return int(used)


def last_run_started(conn) -> datetime | None:
    """When the last successful scheduled TheirStack run began; jobs discovered
    after that are the new ones."""
    cur = conn.cursor()
    cur.execute("""
        SELECT run_at - make_interval(secs => COALESCE(duration_seconds, 0)) FROM fetch_logs
        WHERE run_type IN ('theirstack', 'theirstack_backfill') AND status = 'success'
        ORDER BY run_at DESC LIMIT 1
    """)
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def stored_theirstack_ids(conn) -> list[int]:
    cur = conn.cursor()
    cur.execute("SELECT job_id FROM jobs WHERE job_id LIKE 'ts-%'")
    ids = [int(r[0][3:]) for r in cur.fetchall() if r[0][3:].isdigit()]
    cur.close()
    return ids


def location_ids(city: str, country_code: str) -> list[int]:
    """TheirStack's location ids for a city name, from its location catalog (no
    job data, no credits). A name like Bangkok is both a region (the whole
    province) and a city, and jobs are tagged with either, so both are used."""
    response = requests.get(
        "https://api.theirstack.com/v0/catalog/locations",
        params={"name": city, "country_code": country_code},
        headers={"Authorization": f"Bearer {os.environ['THEIRSTACK_API_KEY']}"},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    items = data.get("data", []) if isinstance(data, dict) else data
    wanted = city.strip().lower()
    return [i["id"] for i in items if (i.get("name") or "").lower() == wanted and i.get("country_code") == country_code]


def in_city(job: dict, city: str) -> bool:
    """Whether a TheirStack job is in the city, from its tagged locations or its location text."""
    wanted = city.strip().lower()
    names = [loc.get(key) for loc in job.get("locations") or [] for key in ("name", "admin1_name")]
    names += [job.get("location"), job.get("short_location"), job.get("long_location")]
    return any(wanted in (name or "").lower() for name in names)


def search_theirstack(roles: list[str], country_codes: list[str], credits_left: int,
                      discovered_since: datetime | None = None, skip_ids: list[int] | None = None,
                      locations: list[int] | None = None) -> list[dict]:
    """Every job matching any of the roles, page by page, never asking for more
    jobs than credits_left. locations limits it to those TheirStack location
    ids. Returns raw TheirStack jobs (1 credit each)."""
    patterns = title_patterns(roles)
    if not patterns or credits_left <= 0:
        return []
    headers = {"Authorization": f"Bearer {os.environ['THEIRSTACK_API_KEY']}"}
    jobs, page = [], 0
    while credits_left > 0:
        limit = min(PAGE_SIZE, credits_left)
        body = {
            "job_title_or": patterns,
            "job_country_code_or": country_codes,
            "posted_at_max_age_days": MAX_AGE_DAYS,
            "limit": limit,
            "page": page,
        }
        if discovered_since:
            body["discovered_at_gte"] = discovered_since.astimezone(timezone.utc).isoformat()
        if skip_ids:
            body["job_id_not"] = skip_ids
        if locations:
            body["job_location_or"] = [{"id": location_id} for location_id in locations]
        response = requests.post(THEIRSTACK_URL, json=body, headers=headers, timeout=120)
        if response.status_code != 200:
            raise RuntimeError(f"TheirStack HTTP {response.status_code}: {response.text[:300]}")
        batch = response.json().get("data") or []
        jobs.extend(batch)
        credits_left -= len(batch)
        if len(batch) < limit:
            break
        page += 1
    return jobs


def country_codes(countries: set[str]) -> list[str]:
    import pycountry
    return sorted({pycountry.countries.lookup(c).alpha_2 for c in countries})


def fetch_theirstack(pairs: list[tuple], conn, run_type: str = "theirstack", since: datetime | None = None) -> int:
    """TheirStack requests for the given (role, country, city, ...) interests: one
    per country and city, with all of that place's roles in it. Results are stored
    through search_agent.store_jobs. Returns new jobs stored."""
    places: dict[tuple, list[str]] = {}
    for role, country, city, *_ in pairs:
        places.setdefault((country, city), []).append(role)
    return sum(
        fetch_place(sorted(set(roles)), country, city, conn, run_type, since)
        for (country, city), roles in sorted(places.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))
    )


def fetch_place(roles: list[str], country: str, city: str | None, conn, run_type: str, since: datetime | None) -> int:
    import time
    from jobs_manager import log_fetch
    from search_agent import store_jobs, wants_internships

    label = ", ".join(roles)[:250]
    budget_left = THEIRSTACK_BUDGET - credits_used(conn)
    start = time.time()
    if budget_left <= 0:
        print(f"TheirStack budget used up ({THEIRSTACK_BUDGET} credits per 30 days); skipping")
        log_fetch(conn, run_type, label, country, city, 0, f"{MAX_AGE_DAYS}d",
                  status="failed", error_message="Monthly credit budget used up",
                  duration_seconds=round(time.time() - start, 2))
        return 0
    try:
        code = country_codes({country})[0]
        locations = None
        if city:
            locations = location_ids(city, code)
            if not locations:
                raise RuntimeError(f"TheirStack doesn't know the city '{city}' in {country}")
        raw = search_theirstack(roles, [code], budget_left, discovered_since=since,
                                skip_ids=stored_theirstack_ids(conn), locations=locations)
        # A safety net in case a job's location tags are off: keep only the interest's city
        kept = [j for j in raw if not city or in_city(j, city)]
        if len(kept) < len(raw):
            print(f"Dropped {len(raw) - len(kept)} job(s) outside {city}")
        # Filter as one interest: internships only when every interest asks for them
        new_count = store_jobs([to_job_row(j) for j in kept], "intern" if all(map(wants_internships, roles)) else "", conn)
    except Exception as e:
        log_fetch(conn, run_type, label, country, city, None, f"{MAX_AGE_DAYS}d",
                  status="failed", error_message=str(e)[:500], duration_seconds=round(time.time() - start, 2))
        raise
    # num_jobs_found is the credits this run spent (one per job returned)
    log_fetch(conn, run_type, label, country, city, None, f"{MAX_AGE_DAYS}d",
              num_jobs_found=len(raw), num_jobs_new=new_count, duration_seconds=round(time.time() - start, 2))
    print(f"TheirStack ({city or country}): {len(raw)} credit(s) spent, {new_count} new job(s), "
          f"{budget_left - len(raw)} of {THEIRSTACK_BUDGET} left for the next 30 days")
    return new_count
