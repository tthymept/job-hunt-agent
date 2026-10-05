# src/job_hunt_agent/api.py
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok"}

COUNTRY_NAMES = {"SG": "Singapore", "TH": "Thailand", "MY": "Malaysia"}

def format_location(raw: dict) -> str:
    city = raw.get("job_city")
    if city:
        return city
    country_code = raw.get("job_country")
    if country_code:
        return COUNTRY_NAMES.get(country_code, country_code)
    return "—"

def reshape_job(raw: dict, index: int) -> dict:
    deadline = raw.get("application_deadline") or raw.get("job_offer_expiration_datetime_utc")
    deadline = deadline[:10] if deadline else "ASAP"
    return {
        "num": f"J-{1000 + index}",
        "co": raw.get("employer_name") or "Unknown",
        "title": raw.get("job_title") or "Untitled role",
        "loc": format_location(raw),
        "dur": raw.get("duration") or "—",
        "min": f"{raw['min_duration_months']} months" if raw.get("min_duration_months") else "—",
        "dl": deadline,
        "src": raw.get("job_publisher") or "—",
        "applyLink": raw.get("job_apply_link"),
        "added": False,
    }

POSTED_DATE_DAYS = {"today": 1, "3days": 3, "week": 7, "month": 30}

def passes_posted_date(row: dict, posted_date: str) -> bool:
    if posted_date not in POSTED_DATE_DAYS:
        return True  # "all" or anything unrecognized -> no filtering
    posted_str = row.get("job_posted_at_datetime_utc")
    if not posted_str:
        return True  # unknown date -> don't exclude it, just can't confirm it's recent
    try:
        posted_dt = datetime.fromisoformat(posted_str)
    except ValueError:
        return True
    if posted_dt.tzinfo is None:
        posted_dt = posted_dt.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=POSTED_DATE_DAYS[posted_date])
    return posted_dt >= cutoff

def passes_location(row: dict, location: str) -> bool:
    if location in ("", "all"):
        return True
    city = (row.get("job_city") or "").lower()
    country = (row.get("job_country") or "").lower()
    if location == "singapore":
        return "singapore" in city or country == "sg"
    if location == "bangkok":
        return "bangkok" in city or country == "th"
    return True

def passes_role(row: dict, role: str) -> bool:
    if not role:
        return True
    return role.lower() in (row.get("job_title") or "").lower()

@app.get("/api/explore-jobs")
def get_explore_jobs(
    page: int = 1,
    page_size: int = 20,
    sort: str = "relevance",
    role: str = "",
    location: str = "",
    posted_date: str = "all",
):
    response = supabase.table("jobs").select("*").execute()
    rows = response.data or []

    rows = [
        r for r in rows
        if passes_role(r, role) and passes_location(r, location) and passes_posted_date(r, posted_date)
    ]

    if sort == "deadline":
        rows.sort(key=lambda r: (
            r.get("application_deadline") is None and r.get("job_offer_expiration_datetime_utc") is None,
            r.get("application_deadline") or r.get("job_offer_expiration_datetime_utc") or ""
        ))
    else:
        rows.sort(key=lambda r: r.get("job_posted_at_datetime_utc") or "", reverse=True)

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]
    jobs = [reshape_job(row, start + i) for i, row in enumerate(page_rows)]
    return {"jobs": jobs, "total": total, "page": page, "page_size": page_size}