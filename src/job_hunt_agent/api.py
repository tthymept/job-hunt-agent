# src/job_hunt_agent/api.py
import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


# ---------- shared helpers ----------

COUNTRY_NAMES = {"SG": "Singapore", "TH": "Thailand", "MY": "Malaysia"}

def format_location(raw: dict) -> str:
    city = raw.get("job_city")
    if city:
        return city
    country_code = raw.get("job_country")
    if country_code:
        return COUNTRY_NAMES.get(country_code, country_code)
    return "—"

def job_core_fields(raw: dict) -> dict:
    deadline = raw.get("application_deadline") or raw.get("job_offer_expiration_datetime_utc")
    deadline = deadline[:10] if deadline else "ASAP"
    return {
        "co": raw.get("employer_name") or "Unknown",
        "title": raw.get("job_title") or "Untitled role",
        "loc": format_location(raw),
        "dur": raw.get("duration") or "—",
        "min": f"{raw['min_duration_months']} months" if raw.get("min_duration_months") else "—",
        "dl": deadline,
        "applyLink": raw.get("job_apply_link"),
        "skills": raw.get("skills") or [],
        "jd": raw.get("job_description") or raw.get("short_description") or "",
    }

def get_current_user_id() -> int:
    # Hardcoded single-user for now. Every endpoint below already threads
    # user_id through, so swapping in real auth later only means changing
    # this one function - nothing else needs to move.
    return 1


# ---------- Explore Jobs ----------

def reshape_job(raw: dict, index: int, tracked_status: dict) -> dict:
    core = job_core_fields(raw)
    job_id = raw.get("job_id")
    status = tracked_status.get(job_id)
    if status is None:
        track_state = "none"
    elif status == "Untracked":
        track_state = "untracked"
    else:
        track_state = "added"
    return {
        "num": f"J-{1000 + index}",
        "jobId": job_id,
        "src": raw.get("job_publisher") or "—",
        "trackState": track_state,
        **core,
    }

POSTED_DATE_DAYS = {"today": 1, "3days": 3, "week": 7, "month": 30}

def passes_posted_date(row: dict, posted_date: str) -> bool:
    if posted_date not in POSTED_DATE_DAYS:
        return True
    posted_str = row.get("job_posted_at_datetime_utc")
    if not posted_str:
        return True
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
    uid = get_current_user_id()
    tracked_response = supabase.table("user_job_tracking").select("job_id, status").eq("user_id", uid).execute()
    tracked_status = {row["job_id"]: row["status"] for row in (tracked_response.data or [])}

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
    jobs = [reshape_job(row, start + i, tracked_status) for i, row in enumerate(page_rows)]
    return {"jobs": jobs, "total": total, "page": page, "page_size": page_size}


# ---------- Dashboard / Tracker ----------

def reshape_tracker_row(row: dict) -> dict:
    job_raw = row.get("jobs") or {}
    core = job_core_fields(job_raw)

    bullets = None
    tailored = row.get("tailored_cv")
    if tailored:
        try:
            parsed = json.loads(tailored) if isinstance(tailored, str) else tailored
            bullets = parsed.get("bullets")
        except (ValueError, AttributeError, TypeError):
            bullets = None

    my_upload_url = None
    if row.get("my_upload_path"):
        try:
            signed = supabase.storage.from_("resumes").create_signed_url(row["my_upload_path"], 3600)
            my_upload_url = signed.get("signedURL") or signed.get("signed_url")
        except Exception:
            my_upload_url = None

    return {
        "trackingId": row["tracking_id"],
        "jobId": row["job_id"],
        "status": row.get("status") or "Saved / Not Applied",
        "bullets": bullets,
        "myUploadUrl": my_upload_url,
        **core,
    }

@app.get("/api/tracker")
def get_tracker():
    uid = get_current_user_id()
    response = (
        supabase.table("user_job_tracking")
        .select("*, jobs(*)")
        .eq("user_id", uid)
        .neq("status", "Untracked")
        .order("tracking_id")
        .execute()
    )
    return [reshape_tracker_row(row) for row in (response.data or [])]

class AddTrackerBody(BaseModel):
    job_id: str

@app.post("/api/tracker")
def add_to_tracker(body: AddTrackerBody):
    uid = get_current_user_id()
    existing = (
        supabase.table("user_job_tracking")
        .select("tracking_id, status")
        .eq("user_id", uid)
        .eq("job_id", body.job_id)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        if row["status"] == "Untracked":
            supabase.table("user_job_tracking").update({
                "status": "Saved / Not Applied",
                "status_updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("tracking_id", row["tracking_id"]).execute()
            return {"status": "retracked"}
        return {"status": "already_tracked"}
    supabase.table("user_job_tracking").insert({
        "user_id": uid,
        "job_id": body.job_id,
        "status": "Saved / Not Applied",
    }).execute()
    return {"status": "added"}

class StatusBody(BaseModel):
    status: str

@app.patch("/api/tracker/{tracking_id}/status")
def update_status(tracking_id: int, body: StatusBody):
    supabase.table("user_job_tracking").update({
        "status": body.status,
        "status_updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("tracking_id", tracking_id).execute()
    return {"status": "ok"}

# STUB: no real tailoring agent is wired into this endpoint yet.
# This exists so the frontend flow (Generate -> show bullets -> Refresh)
# is complete now, ready to swap in a real agent call later with zero
# frontend changes.
PLACEHOLDER_BULLETS = [
    "Placeholder bullet — real tailoring agent not connected yet.",
    "Swap this endpoint's logic for your actual CV tailor agent later.",
]

@app.post("/api/tracker/{tracking_id}/generate-bullets")
def generate_bullets(tracking_id: int):
    payload = json.dumps({"bullets": PLACEHOLDER_BULLETS})
    supabase.table("user_job_tracking").update({"tailored_cv": payload}).eq("tracking_id", tracking_id).execute()
    return {"bullets": PLACEHOLDER_BULLETS}

@app.post("/api/tracker/{tracking_id}/upload")
async def upload_my_cv(tracking_id: int, file: UploadFile = File(...)):
    uid = get_current_user_id()
    row = (
        supabase.table("user_job_tracking")
        .select("job_id")
        .eq("tracking_id", tracking_id)
        .single()
        .execute()
    )
    job_id = row.data["job_id"]
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "pdf"
    path = f"{uid}/tailored/{job_id}.{ext}"
    contents = await file.read()
    supabase.storage.from_("resumes").upload(path, contents, {"content-type": file.content_type, "upsert": "true"})
    supabase.table("user_job_tracking").update({"my_upload_path": path}).eq("tracking_id", tracking_id).execute()
    return {"status": "uploaded", "path": path}

def track_job_for_user(uid: int, job_id: str) -> str:
    existing = (
        supabase.table("user_job_tracking")
        .select("tracking_id, status")
        .eq("user_id", uid)
        .eq("job_id", job_id)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        if row["status"] == "Untracked":
            supabase.table("user_job_tracking").update({
                "status": "Saved / Not Applied",
                "status_updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("tracking_id", row["tracking_id"]).execute()
            return "retracked"
        return "already_tracked"
    supabase.table("user_job_tracking").insert({
        "user_id": uid,
        "job_id": job_id,
        "status": "Saved / Not Applied",
    }).execute()
    return "added"

class AddTrackerBody(BaseModel):
    job_id: str

@app.post("/api/tracker")
def add_to_tracker(body: AddTrackerBody):
    uid = get_current_user_id()
    status = track_job_for_user(uid, body.job_id)
    return {"status": status}


class ManualJobBody(BaseModel):
    company: str
    title: str
    location: str | None = None
    duration: str | None = None
    min_duration_months: int | None = None
    deadline: str | None = None
    apply_link: str | None = None
    skills: list[str] = []
    description: str | None = None

@app.post("/api/jobs/manual")
def add_manual_job(body: ManualJobBody):
    uid = get_current_user_id()
    job_id = f"manual-{uuid.uuid4()}"

    supabase.table("jobs").insert({
        "job_id": job_id,
        "employer_name": body.company,
        "job_title": body.title,
        "job_city": body.location,
        "duration": body.duration,
        "min_duration_months": body.min_duration_months,
        "application_deadline": body.deadline,
        "job_apply_link": body.apply_link,
        "job_description": body.description,
        "short_description": body.description,
        "skills": body.skills,
        "job_publisher": "Manual",
        "enrichment_status": "done",
        "job_posted_at_datetime_utc": datetime.now(timezone.utc).isoformat(),
    }).execute()

    track_job_for_user(uid, job_id)
    return {"status": "added", "job_id": job_id}