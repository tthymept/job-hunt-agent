# src/job_hunt_agent/api.py
import os
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
    allow_origins=["http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok"}

# NOTE: no @app.get decorator here — this is just a plain helper function
def reshape_job(raw: dict, index: int) -> dict:
    deadline = raw.get("application_deadline") or raw.get("job_offer_expiration_datetime_utc")
    if deadline:
        deadline = deadline[:10]
    else:
        deadline = "ASAP"

    return {
        "num": f"J-{1000 + index}",
        "co": raw.get("employer_name") or "Unknown",
        "title": raw.get("job_title") or "Untitled role",
        "loc": raw.get("job_city") or raw.get("job_country") or "—",
        "dur": raw.get("duration") or "—",
        "min": f"{raw['min_duration_months']} months" if raw.get("min_duration_months") else "—",
        "dl": deadline,
        "src": raw.get("job_publisher") or "—",
        "applyLink": raw.get("job_apply_link"),
        "added": False,
    }

@app.get("/api/explore-jobs")
def get_explore_jobs(page: int = 1, page_size: int = 20):
    start = (page - 1) * page_size
    end = start + page_size - 1

    response = (
        supabase.table("jobs")
        .select("*", count="exact")
        .range(start, end)
        .execute()
    )

    jobs = [reshape_job(row, start + i) for i, row in enumerate(response.data)]
    return {
        "jobs": jobs,
        "total": response.count or 0,
        "page": page,
        "page_size": page_size,
    }