# src/job_hunt_agent/api.py
import os
import json
import uuid
import re
import socket
import ipaddress
import hashlib
import hmac
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel
from supabase import create_client, Client
from extract_agent import extract_cv_structure
from tailor_agent import tailor_cv
import psycopg2
import pycountry
from jobs_manager import add_interest, backfill_new_pair

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# Single-user lock for the deployed app. When APP_ACCESS_KEY is set, every /api
# request (except the health check) must send it in the X-Access-Key header.
# Visitors without the key can browse as a guest (X-Guest header): reads are
# allowed, anything that changes data is refused with 403.
# Locally it is usually unset, so nothing changes during development.
APP_ACCESS_KEY = os.environ.get("APP_ACCESS_KEY", "")
READ_METHODS = ("GET", "HEAD")

@app.middleware("http")
async def require_access_key(request: Request, call_next):
    path = request.url.path
    if (
        APP_ACCESS_KEY
        and path.startswith("/api/")
        and path != "/api/health"
        and request.method != "OPTIONS"  # CORS preflight carries no custom headers
    ):
        sent = request.headers.get("x-access-key", "")
        if not hmac.compare_digest(sent.encode(), APP_ACCESS_KEY.encode()):
            if sent or not request.headers.get("x-guest"):
                return JSONResponse(status_code=401, content={"detail": "Access key required."})
            if request.method not in READ_METHODS:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "View-only guest mode. Enter the access key to make changes."},
                )
            request.state.guest = True
    return await call_next(request)

def is_guest(request: Request) -> bool:
    return getattr(request.state, "guest", False)

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

@app.get("/api/me")
def get_me(request: Request):
    uid = get_current_user_id()
    rows = supabase.table("users").select("name, email").eq("user_id", uid).execute().data
    row = rows[0] if rows else {}
    # A guest sees whose tracker this is, but not how to contact them
    email = "" if is_guest(request) else row.get("email") or ""
    return {"name": row.get("name") or "", "email": email}


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
        "posted": (raw.get("job_posted_at_datetime_utc") or "—")[:10],
        "src": raw.get("job_publisher") or "—",
        "trackState": track_state,
        **core,
    }

POSTED_DATE_DAYS = {"today": 1, "3days": 3, "week": 7, "month": 30}

def location_filter(location: str) -> str | None:
    """PostgREST `or` expression for a location name: the city contains it,
    or (when it is a country name) the country code matches."""
    # Only letters and spaces, so the value can't break the or=(...) syntax
    clean = re.sub(r"[^a-z ]", "", (location or "").lower()).strip()
    if not clean or clean == "all":
        return None
    parts = [f'job_city.ilike."*{clean}*"']
    try:
        parts.append(f"job_country.eq.{pycountry.countries.lookup(clean).alpha_2}")
    except LookupError:
        pass
    return ",".join(parts)

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
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    tracked_response = supabase.table("user_job_tracking").select("job_id, status").eq("user_id", uid).execute()
    tracked_status = {row["job_id"]: row["status"] for row in (tracked_response.data or [])}

    # Filtering, sorting and paging all happen in Postgres, so only one page of rows comes back
    query = supabase.table("jobs").select("*", count="exact").not_.like("job_id", "manual-%")
    if role.strip():
        query = query.ilike("job_title", f"%{role.strip()}%")
    loc = location_filter(location)
    if loc:
        query = query.or_(loc)
    if posted_date in POSTED_DATE_DAYS:
        cutoff = datetime.now(timezone.utc) - timedelta(days=POSTED_DATE_DAYS[posted_date])
        query = query.gte("job_posted_at_datetime_utc", cutoff.isoformat())

    if sort == "deadline":
        query = (
            query.order("application_deadline", nullsfirst=False)
            .order("job_offer_expiration_datetime_utc", nullsfirst=False)
        )
    else:
        query = query.order("job_posted_at_datetime_utc", desc=True, nullsfirst=False)

    start = (page - 1) * page_size
    response = query.range(start, start + page_size - 1).execute()
    jobs = [reshape_job(row, start + i, tracked_status) for i, row in enumerate(response.data or [])]
    return {"jobs": jobs, "total": response.count or 0, "page": page, "page_size": page_size}

@app.get("/api/explore-locations")
def get_explore_locations():
    # The location filter offers the places you search in: each interest's city, or its country
    uid = get_current_user_id()
    rows = (
        supabase.table("job_interests")
        .select("city, country")
        .eq("user_id", uid)
        .neq("status", "removed")
        .execute()
        .data
    ) or []
    places = {(r["city"] or r["country"]).lower() for r in rows if r["city"] or r["country"]}
    return [{"value": p, "label": p.title()} for p in sorted(places)]


# ---------- Tracker tabs ----------
# The dashboard is split into tabs (e.g. "Internships 2027", "Internships 2028").
# Every tracked job belongs to one tab. A disabled tab can still be opened and
# edited, but new jobs can't be added to it until it is enabled again.

FIRST_TAB_NAME = "My jobs"
MAX_TAB_NAME_CHARS = 40

def default_tab(tabs: list[dict]) -> dict | None:
    """The tab flagged as default, or the oldest one when none is flagged."""
    if not tabs:
        return None
    flagged = [t for t in tabs if t.get("is_default")]
    return (flagged or tabs)[0]

def pick_target_tab(tabs: list[dict], requested_id: int | None) -> dict:
    """The tab a new job goes into. With no tab requested (only one tab to
    choose from) it is the default tab if that is enabled,
    otherwise the first enabled one. Raises ValueError when it can't be used."""
    if requested_id is not None:
        tab = next((t for t in tabs if t["tab_id"] == requested_id), None)
        if tab is None:
            raise ValueError("That tab doesn't exist.")
        if not tab["enabled"]:
            raise ValueError("Adding jobs is turned off for that tab. Turn it on to add jobs there.")
        return tab
    enabled = [t for t in tabs if t["enabled"]]
    if not enabled:
        raise ValueError("Every tab has adding turned off. Turn it on for one tab first.")
    chosen = default_tab(tabs)
    return chosen if chosen["enabled"] else enabled[0]

def clean_tab_name(name: str) -> str:
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise HTTPException(status_code=400, detail="Give the tab a name.")
    if len(cleaned) > MAX_TAB_NAME_CHARS:
        raise HTTPException(status_code=400, detail=f"Tab names can be up to {MAX_TAB_NAME_CHARS} characters.")
    return cleaned

def name_taken(tabs: list[dict], name: str, except_id: int | None = None) -> bool:
    """True when another tab already has this name. Upper and lower case count as the same."""
    wanted = name.casefold()
    return any(t["name"].casefold() == wanted for t in tabs if t["tab_id"] != except_id)

def free_tab_name(tabs: list[dict], name: str, except_id: int | None = None) -> str:
    cleaned = clean_tab_name(name)
    if name_taken(tabs, cleaned, except_id):
        raise HTTPException(status_code=400, detail=f'You already have a tab called "{cleaned}".')
    return cleaned

def load_tabs(uid: int) -> list[dict]:
    """The user's tabs, oldest first. Creates the first tab if there is none yet."""
    tabs = (
        supabase.table("tracker_tabs").select("*").eq("user_id", uid).order("tab_id").execute().data
    ) or []
    if not tabs:
        tabs = supabase.table("tracker_tabs").insert({
            "user_id": uid, "name": FIRST_TAB_NAME, "is_default": True,
        }).execute().data
    return tabs

def tabs_payload(tabs: list[dict]) -> list[dict]:
    default_id = default_tab(tabs)["tab_id"]
    return [
        {"id": t["tab_id"], "name": t["name"], "enabled": t["enabled"], "isDefault": t["tab_id"] == default_id}
        for t in tabs
    ]

def target_tab_id(uid: int, requested_id: int | None) -> int:
    try:
        return pick_target_tab(load_tabs(uid), requested_id)["tab_id"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

def find_tab(tabs: list[dict], tab_id: int) -> dict:
    tab = next((t for t in tabs if t["tab_id"] == tab_id), None)
    if tab is None:
        raise HTTPException(status_code=404, detail="Tab not found.")
    return tab

@app.get("/api/tabs")
def list_tabs():
    return tabs_payload(load_tabs(get_current_user_id()))

class NewTabBody(BaseModel):
    name: str

@app.post("/api/tabs")
def create_tab(body: NewTabBody):
    uid = get_current_user_id()
    tabs = load_tabs(uid)  # also makes sure the first tab exists before a second one is added
    supabase.table("tracker_tabs").insert({"user_id": uid, "name": free_tab_name(tabs, body.name)}).execute()
    return tabs_payload(load_tabs(uid))

class TabUpdateBody(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None

@app.patch("/api/tabs/{tab_id}")
def update_tab(tab_id: int, body: TabUpdateBody):
    uid = get_current_user_id()
    tabs = load_tabs(uid)
    tab = find_tab(tabs, tab_id)

    changes = {}
    if body.name is not None:
        changes["name"] = free_tab_name(tabs, body.name, except_id=tab_id)
    if body.enabled is not None:
        others_enabled = any(t["enabled"] for t in tabs if t["tab_id"] != tab_id)
        if not body.enabled and not others_enabled:
            raise HTTPException(status_code=400, detail="At least one tab has to accept new jobs.")
        changes["enabled"] = body.enabled
    if body.is_default:
        # Only one tab is the default: clear the flag everywhere, then set it here
        supabase.table("tracker_tabs").update({"is_default": False}).eq("user_id", uid).execute()
        changes["is_default"] = True
    if changes:
        supabase.table("tracker_tabs").update(changes).eq("tab_id", tab["tab_id"]).eq("user_id", uid).execute()
    return tabs_payload(load_tabs(uid))

def new_positions(current_ids: list[int], requested_ids: list[int]) -> dict[int, int]:
    """tracking_id -> position (1 = top) for a tab whose jobs are current_ids, in
    their saved order, after putting requested_ids first in the order given. Jobs
    the request leaves out (say, added from another device since the page loaded)
    keep their order below them. Raises ValueError for a job not in the tab."""
    if set(requested_ids) - set(current_ids):
        raise ValueError("Some of those jobs aren't in this tab. Reload the page and try again.")
    requested = list(dict.fromkeys(requested_ids))
    left_out = [i for i in current_ids if i not in set(requested)]
    return {tracking_id: n for n, tracking_id in enumerate(requested + left_out, 1)}

def end_position(uid: int, tab_id: int) -> int:
    """The position just below the last job in a tab: where a new or moved job goes."""
    rows = (
        supabase.table("user_job_tracking")
        .select("position")
        .eq("user_id", uid)
        .eq("tab_id", tab_id)
        .order("position", desc=True, nullsfirst=False)
        .limit(1)
        .execute()
        .data
    )
    return ((rows[0].get("position") or 0) if rows else 0) + 1

class TabOrderBody(BaseModel):
    tracking_ids: list[int]

@app.put("/api/tabs/{tab_id}/order")
def save_tab_order(tab_id: int, body: TabOrderBody):
    """Saves "My order" for a tab: the up and down arrows, and Save as my order."""
    uid = get_current_user_id()
    tabs = load_tabs(uid)
    find_tab(tabs, tab_id)
    query = (
        supabase.table("user_job_tracking")
        .select("tracking_id, position")
        .eq("user_id", uid)
        .neq("status", "Untracked")
    )
    # A job with no tab shows in the default tab (see get_tracker), so it is ordered there
    if default_tab(tabs)["tab_id"] == tab_id:
        query = query.or_(f"tab_id.eq.{tab_id},tab_id.is.null")
    else:
        query = query.eq("tab_id", tab_id)
    rows = query.order("position", nullsfirst=False).order("tracking_id").execute().data or []
    try:
        positions = new_positions([r["tracking_id"] for r in rows], body.tracking_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Only the rows that moved are written: one arrow click changes two
    saved = {r["tracking_id"]: r.get("position") for r in rows}
    for tracking_id, position in positions.items():
        if saved[tracking_id] != position:
            supabase.table("user_job_tracking").update({"position": position, "tab_id": tab_id}).eq(
                "tracking_id", tracking_id
            ).eq("user_id", uid).execute()
    return {"status": "ok"}

@app.delete("/api/tabs/{tab_id}")
def delete_tab(tab_id: int):
    uid = get_current_user_id()
    tabs = load_tabs(uid)
    find_tab(tabs, tab_id)
    if len(tabs) == 1:
        raise HTTPException(status_code=400, detail="You need at least one tab.")
    in_tab = (
        supabase.table("user_job_tracking")
        .select("tracking_id")
        .eq("user_id", uid)
        .eq("tab_id", tab_id)
        .neq("status", "Untracked")
        .limit(1)
        .execute()
        .data
    )
    if in_tab:
        raise HTTPException(status_code=400, detail="Only an empty tab can be deleted. Move or untrack its jobs first.")
    # Untracked rows that pointed here lose their tab (the column is ON DELETE SET NULL)
    supabase.table("tracker_tabs").delete().eq("tab_id", tab_id).eq("user_id", uid).execute()

    remaining = load_tabs(uid)
    if not any(t["enabled"] for t in remaining):
        # The deleted tab was the only one accepting jobs: reopen the default one
        supabase.table("tracker_tabs").update({"enabled": True}).eq("tab_id", default_tab(remaining)["tab_id"]).execute()
        remaining = load_tabs(uid)
    return tabs_payload(remaining)


# ---------- Dashboard / Tracker ----------

# The files you can attach to a tracked job: kind -> (column holding the storage path, storage folder)
UPLOAD_KINDS = {
    "cv": ("my_upload_path", "tailored"),
    "cover_letter": ("cover_letter_path", "cover-letters"),
}

def upload_slot(kind: str) -> tuple[str, str]:
    if kind not in UPLOAD_KINDS:
        raise HTTPException(status_code=400, detail="Unknown upload kind.")
    return UPLOAD_KINDS[kind]

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# The file types a tracked job's CV or cover letter can be: extension -> (content type, first bytes)
UPLOAD_TYPES = {
    "pdf": ("application/pdf", b"%PDF"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04"),
    "doc": ("application/msword", b"\xd0\xcf\x11\xe0"),
}

def check_upload(filename: str | None, contents: bytes) -> tuple[str, str]:
    """The (extension, content type) to store a tracker upload with. The extension
    comes from UPLOAD_TYPES, never straight from the filename, so it can't shape the
    storage path. Raises 400 for other file types, empty or oversized files."""
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext not in UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a PDF or Word file (.pdf, .doc, .docx).")
    if not contents:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="That file is over 10 MB.")
    content_type, signature = UPLOAD_TYPES[ext]
    if not contents.startswith(signature):
        raise HTTPException(status_code=400, detail=f"That doesn't look like a valid .{ext} file.")
    return ext, content_type

# A file link only has to last until the browser opens it
FILE_LINK_SECONDS = 60

def fresh_file_link(path: str) -> dict:
    """{"url": ...} for a stored file, made when it is clicked. Links used to be
    made when the page loaded and expired after an hour, so a page left open
    longer showed an InvalidJWT error instead of the file."""
    try:
        signed = supabase.storage.from_("resumes").create_signed_url(path, FILE_LINK_SECONDS)
        url = signed.get("signedURL") or signed.get("signed_url")
    except Exception as e:
        print(f"Signing {path} failed: {e}")
        url = None
    if not url:
        raise HTTPException(status_code=502, detail="Couldn't get a link to that file from storage.")
    return {"url": url}

def reshape_tracker_row(row: dict, locked: bool = False) -> dict:
    """locked (a guest is looking): leave out the uploaded files and the tailored
    bullets, which are the owner's CV, the edit form's fields, and anything you
    wrote yourself (notes, contact, stage notes)."""
    job_raw = row.get("jobs") or {}
    overrides = row.get("overrides") or {}
    merged_raw = {**job_raw, **overrides}
    core = job_core_fields(merged_raw)
    events = row.get("status_events") or []
    history = history_payload(events, locked=locked)

    if locked:
        return {
            "trackingId": row["tracking_id"],
            "jobId": row["job_id"],
            "status": row.get("status") or "Saved / Not Applied",
            "bullets": None,
            "hasMyUpload": False,
            "hasCoverLetter": False,
            "submittedAt": submitted_at_of(events),
            "history": history,
            "notes": None,
            "contact": None,
            "edit": None,
            "locked": True,
            **core,
        }

    bullets = None
    tailored = row.get("tailored_cv")
    if tailored:
        try:
            parsed = json.loads(tailored) if isinstance(tailored, str) else tailored
            bullets = tailored_groups(parsed) if "sections" in parsed else None
        except (ValueError, AttributeError, TypeError):
            bullets = None

    return {
        "trackingId": row["tracking_id"],
        "jobId": row["job_id"],
        "status": row.get("status") or "Saved / Not Applied",
        "bullets": bullets,
        # Only whether each file exists: the link is made on click (see tracker_file_link)
        "hasMyUpload": bool(row.get("my_upload_path")),
        "hasCoverLetter": bool(row.get("cover_letter_path")),
        "submittedAt": submitted_at_of(events),
        "history": history,
        "notes": row.get("notes") or "",
        "contact": row.get("contact") or "",
        "edit": editable_fields(merged_raw),
        **core,
    }

# Guests only see the first few tracked jobs. X-Total-Count tells the dashboard
# that more are hidden behind the access key; for a guest it is capped at one
# over the limit, so it never gives away the real number
GUEST_TRACKER_LIMIT = 4

@app.get("/api/tracker")
def get_tracker(request: Request, response: Response):
    uid = get_current_user_id()
    rows = (
        supabase.table("user_job_tracking")
        .select("*, jobs(*), status_events(*)")
        .eq("user_id", uid)
        .neq("status", "Untracked")
        # My order (the arrows on the dashboard); jobs from before it existed by when they were added
        .order("position", nullsfirst=False)
        .order("tracking_id")
        .execute()
        .data
    ) or []
    total = len(rows)
    guest = is_guest(request)
    if guest:
        total = min(total, GUEST_TRACKER_LIMIT + 1)
        rows = rows[:GUEST_TRACKER_LIMIT]
    response.headers["X-Total-Count"] = str(total)
    # A row with no tab (added before tabs existed, or its tab was deleted) shows in the default tab
    fallback_tab_id = default_tab(load_tabs(uid))["tab_id"]
    return [
        {**reshape_tracker_row(row, locked=guest), "tabId": row.get("tab_id") or fallback_tab_id}
        for row in rows
    ]

# ---------- Status history ----------
# Every stage a tracked job reaches is a row in status_events, with the day it
# happened. The history is the path to the current stage: each stage at most
# once, always in pipeline order.

# The dashboard's stages in order (STATUS in front-end/src/data.js)
PIPELINE = [
    "Saved / Not Applied", "Submitted", "Online Assignment",
    "Interview Round 1", "Interview Round 2", "Offered", "Rejected",
]
# Plus Untracked, which hides the job from the dashboard
VALID_STATUSES = set(PIPELINE) | {"Untracked"}

MAX_STAGE_NOTE_CHARS = 1000
MAX_NOTES_CHARS = 5000
MAX_CONTACT_CHARS = 300

def pipeline_index(status: str) -> int:
    return PIPELINE.index(status) if status in PIPELINE else -1

def plan_status_change(history: list[dict], new_status: str) -> tuple[list[int], bool]:
    """How the history changes when the status changes to new_status:
    (event ids to delete, whether to add a row for new_status dated now).
    - Untracked isn't a stage, so nothing changes.
    - Saved / Not Applied is the start, so the whole history goes.
    - Any stage after the new one goes. Picking a stage already in the history
      keeps it with its date, so undoing a mis-click loses nothing; picking a new
      one adds it, so Rejected -> Offered replaces Rejected instead of keeping both."""
    if new_status == "Untracked":
        return [], False
    if new_status == "Saved / Not Applied":
        return [e["event_id"] for e in history], False
    new_index = pipeline_index(new_status)
    delete = [e["event_id"] for e in history if pipeline_index(e["status"]) > new_index]
    return delete, not any(e["status"] == new_status for e in history)

def history_payload(events: list[dict], locked: bool = False) -> list[dict]:
    """The history for the dashboard, in pipeline order. A guest doesn't get the notes."""
    ordered = sorted(events, key=lambda e: pipeline_index(e["status"]))
    return [
        {
            "id": e["event_id"],
            "status": e["status"],
            "at": e["happened_at"],
            "scheduledAt": e.get("scheduled_at"),
            "done": bool(e.get("done")),
            "doneAt": e.get("done_at"),
            "note": None if locked else (e.get("note") or ""),
        }
        for e in ordered
    ]

def submitted_at_of(events: list[dict]) -> str | None:
    """When the job was submitted: the date on its Submitted row."""
    return next((e["happened_at"] for e in events if e["status"] == "Submitted"), None)

def past_day(value: str, today: date, what: str) -> date:
    """A "YYYY-MM-DD" typed by the user, refused when invalid or in the future."""
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"The {what} isn't a valid date.")
    if day > today + timedelta(days=1):  # a day of slack for time zones ahead of UTC
        raise HTTPException(status_code=400, detail=f"The {what} can't be in the future.")
    return day

def noon_utc(day: date) -> str:
    """A day stored as a timestamp at noon UTC, so it shows as that day in any time zone."""
    return f"{day.isoformat()}T12:00:00+00:00"

def clean_scheduled(value: str | None) -> str | None:
    """An OA due date or offer reply-by ("YYYY-MM-DD", kept at noon UTC) or an
    interview time (a full ISO timestamp from the browser). Empty clears it."""
    if not value:
        return None
    try:
        if len(value) == 10:
            return noon_utc(date.fromisoformat(value))
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="That date or time isn't valid.")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat()

def clean_text(value: str | None, limit: int, what: str) -> str | None:
    text = (value or "").strip()
    if len(text) > limit:
        raise HTTPException(status_code=400, detail=f"The {what} can be up to {limit} characters.")
    return text or None

def load_events(uid: int, tracking_id: int) -> list[dict]:
    return (
        supabase.table("status_events").select("*").eq("tracking_id", tracking_id).eq("user_id", uid).execute().data
    ) or []

def change_history(uid: int, tracking_id: int, events: list[dict], new_status: str, now: str) -> list[dict]:
    """Applies plan_status_change and returns the history as it is afterwards."""
    delete, add = plan_status_change(events, new_status)
    if delete:
        supabase.table("status_events").delete().in_("event_id", delete).eq("user_id", uid).execute()
    if add:
        supabase.table("status_events").insert({
            "tracking_id": tracking_id, "user_id": uid, "status": new_status, "happened_at": now,
        }).execute()
    return load_events(uid, tracking_id) if delete or add else events

class StatusBody(BaseModel):
    status: str

@app.patch("/api/tracker/{tracking_id}/status")
def update_status(tracking_id: int, body: StatusBody):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status.")
    uid = get_current_user_id()
    rows = (
        supabase.table("user_job_tracking")
        .select("tracking_id, status_events(*)")
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    now = datetime.now(timezone.utc).isoformat()
    events = change_history(uid, tracking_id, rows[0].get("status_events") or [], body.status, now)
    supabase.table("user_job_tracking").update({
        "status": body.status,
        "status_updated_at": now,
    }).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
    return {"status": "ok", "submittedAt": submitted_at_of(events), "history": history_payload(events)}

class StageUpdateBody(BaseModel):
    # Each field is only changed when sent
    at: str | None = None            # "YYYY-MM-DD": the day the job reached this stage
    scheduled_at: str | None = None  # OA due date, interview time, offer reply-by
    done: bool | None = None
    note: str | None = None

@app.patch("/api/tracker/{tracking_id}/history/{event_id}")
def update_stage(tracking_id: int, event_id: int, body: StageUpdateBody):
    uid = get_current_user_id()
    found = (
        supabase.table("status_events")
        .select("event_id")
        .eq("event_id", event_id)
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not found:
        raise HTTPException(status_code=404, detail="That stage isn't in this job's history.")
    sent = body.model_fields_set
    changes = {}
    if "at" in sent:
        if not body.at:
            raise HTTPException(status_code=400, detail="A stage needs a date.")
        changes["happened_at"] = noon_utc(past_day(body.at, datetime.now(timezone.utc).date(), "date"))
    if "scheduled_at" in sent:
        changes["scheduled_at"] = clean_scheduled(body.scheduled_at)
    if "done" in sent and body.done is not None:
        changes["done"] = body.done
        changes["done_at"] = datetime.now(timezone.utc).isoformat() if body.done else None
    if "note" in sent:
        changes["note"] = clean_text(body.note, MAX_STAGE_NOTE_CHARS, "note")
    if changes:
        supabase.table("status_events").update(changes).eq("event_id", event_id).eq("user_id", uid).execute()
    events = load_events(uid, tracking_id)
    return {"submittedAt": submitted_at_of(events), "history": history_payload(events)}

class NotesBody(BaseModel):
    # Each field is only changed when sent
    notes: str | None = None
    contact: str | None = None

@app.patch("/api/tracker/{tracking_id}/notes")
def update_notes(tracking_id: int, body: NotesBody):
    uid = get_current_user_id()
    sent = body.model_fields_set
    changes = {}
    if "notes" in sent:
        changes["notes"] = clean_text(body.notes, MAX_NOTES_CHARS, "notes")
    if "contact" in sent:
        changes["contact"] = clean_text(body.contact, MAX_CONTACT_CHARS, "contact")
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to save.")
    saved = (
        supabase.table("user_job_tracking")
        .update(changes)
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not saved:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    return {"notes": saved[0].get("notes") or "", "contact": saved[0].get("contact") or ""}

class MoveTabBody(BaseModel):
    tab_id: int

@app.patch("/api/tracker/{tracking_id}/tab")
def move_to_tab(tracking_id: int, body: MoveTabBody):
    uid = get_current_user_id()
    tab_id = target_tab_id(uid, body.tab_id)
    moved = (
        supabase.table("user_job_tracking")
        .update({"tab_id": tab_id, "position": end_position(uid, tab_id)})
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not moved:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    return {"status": "ok", "tabId": tab_id}

# Wire CV
@app.post("/api/tracker/{tracking_id}/generate-bullets")
def generate_bullets(tracking_id: int):
    uid = get_current_user_id()

    # 1. This user's master CV, as read when they uploaded it on the My CV page
    user_rows = supabase.table("users").select("cv_structure").eq("user_id", uid).execute().data
    cv_structure = user_rows[0].get("cv_structure") if user_rows else None
    if not cv_structure:
        raise HTTPException(status_code=400, detail="Upload your CV on the My CV page first.")

    # 2. This job's description, with this user's edits applied on top
    rows = (
        supabase.table("user_job_tracking")
        .select("*, jobs(*)")
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    row = rows[0]
    merged = {**(row.get("jobs") or {}), **(row.get("overrides") or {})}
    description = merged.get("job_description") or ""
    if not description.strip():
        raise HTTPException(status_code=400, detail="This job has no description to tailor against. Use Edit job to add one.")

    # 3. Run the tailor agent and save its output on the tracking row
    try:
        tailored = tailor_cv(cv_structure, description)
    except Exception as e:
        print(f"Tailoring failed: {e}")
        raise HTTPException(status_code=502, detail="The tailor agent failed (it may be rate limited). Try again in a minute.")

    supabase.table("user_job_tracking").update({"tailored_cv": json.dumps(tailored)}).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
    return {"bullets": tailored_groups(tailored)}

#---

@app.post("/api/tracker/{tracking_id}/upload")
async def upload_my_cv(tracking_id: int, file: UploadFile = File(...), kind: str = "cv"):
    column, folder = upload_slot(kind)
    uid = get_current_user_id()
    rows = (
        supabase.table("user_job_tracking")
        .select(f"job_id, {column}")
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    # Read one byte past the limit: enough to tell the file is too big without loading all of it
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    ext, content_type = check_upload(file.filename, contents)
    job_id = rows[0]["job_id"]
    old_path = rows[0].get(column)
    path = f"{uid}/{folder}/{job_id}.{ext}"
    supabase.storage.from_("resumes").upload(path, contents, {"content-type": content_type, "upsert": "true"})
    supabase.table("user_job_tracking").update({column: path}).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
    if old_path and old_path != path:
        # Replacing a .pdf with a .docx (or the other way) saved under a new name: drop the old file
        try:
            supabase.storage.from_("resumes").remove([old_path])
        except Exception as e:
            print(f"Couldn't remove the replaced upload {old_path}: {e}")
    return {"status": "uploaded", "path": path}

@app.get("/api/tracker/{tracking_id}/file-link")
def tracker_file_link(tracking_id: int, request: Request, kind: str = "cv"):
    if is_guest(request):
        raise HTTPException(status_code=403, detail="View-only guest mode. Enter the access key to open files.")
    column, _ = upload_slot(kind)
    uid = get_current_user_id()
    rows = (
        supabase.table("user_job_tracking")
        .select(column)
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    path = rows[0].get(column)
    if not path:
        raise HTTPException(status_code=404, detail="No file uploaded here.")
    return fresh_file_link(path)

@app.delete("/api/tracker/{tracking_id}/upload")
def delete_my_cv(tracking_id: int, kind: str = "cv"):
    column, _ = upload_slot(kind)
    uid = get_current_user_id()
    rows = (
        supabase.table("user_job_tracking")
        .select(column)
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    path = rows[0].get(column)
    if path:
        supabase.storage.from_("resumes").remove([path])
    supabase.table("user_job_tracking").update({column: None}).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
    return {"status": "deleted"}

def track_job_for_user(uid: int, job_id: str, tab_id: int) -> str:
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
                "tab_id": tab_id,
                "position": end_position(uid, tab_id),
            }).eq("tracking_id", row["tracking_id"]).execute()
            # Tracked again from the start: the old history goes with it
            supabase.table("status_events").delete().eq("tracking_id", row["tracking_id"]).eq("user_id", uid).execute()
            return "retracked"
        return "already_tracked"
    supabase.table("user_job_tracking").insert({
        "user_id": uid,
        "job_id": job_id,
        "status": "Saved / Not Applied",
        "tab_id": tab_id,
        "position": end_position(uid, tab_id),  # new jobs go to the bottom of My order
    }).execute()
    return "added"

class AddTrackerBody(BaseModel):
    job_id: str
    tab_id: int | None = None  # None: the server picks the tab (see pick_target_tab)

@app.post("/api/tracker")
def add_to_tracker(body: AddTrackerBody):
    uid = get_current_user_id()
    status = track_job_for_user(uid, body.job_id, target_tab_id(uid, body.tab_id))
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
    tab_id: int | None = None  # only used when adding; editing never moves a job

@app.post("/api/jobs/manual")
def add_manual_job(body: ManualJobBody):
    uid = get_current_user_id()
    tab_id = target_tab_id(uid, body.tab_id)
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
        "skills": body.skills,
        "job_publisher": "Manual",
        "enrichment_status": "done",
        "job_posted_at_datetime_utc": datetime.now(timezone.utc).isoformat(),
    }).execute()

    track_job_for_user(uid, job_id, tab_id)
    return {"status": "added", "job_id": job_id}

# editable field
FIELD_TO_COLUMN = {
    "company": "employer_name",
    "title": "job_title",
    "location": "job_city",
    "duration": "duration",
    "min_duration_months": "min_duration_months",
    "deadline": "application_deadline",
    "apply_link": "job_apply_link",
    "skills": "skills",
    "description": "job_description",
}

def editable_fields(raw: dict) -> dict:
    loc = format_location(raw)
    deadline = raw.get("application_deadline") or raw.get("job_offer_expiration_datetime_utc") or ""
    return {
        "company": raw.get("employer_name") or "",
        "title": raw.get("job_title") or "",
        "location": "" if loc == "—" else loc,
        "duration": raw.get("duration") or "",
        "min_duration_months": raw.get("min_duration_months"),
        # the form uses a date picker, so only ISO dates can be shown in it
        "deadline": deadline[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", deadline) else "",
        "apply_link": raw.get("job_apply_link") or "",
        "skills": raw.get("skills") or [],
        "description": raw.get("job_description") or raw.get("short_description") or "",
    }

def submitted_at_from_date(value: str | None, status: str, today: date) -> str | None:
    """The date for the Submitted stage, from the Edit job form ("YYYY-MM-DD", or
    None/"" to clear it), kept at noon UTC. Raises 400 for a bad or future date,
    or a date on a job that hasn't been submitted yet."""
    if not value:
        return None
    if status in ("Saved / Not Applied", "Untracked"):
        raise HTTPException(status_code=400, detail="Mark the job as Submitted first, then you can change the date.")
    return noon_utc(past_day(value, today, "submitted date"))

def set_submitted_date(uid: int, tracking_id: int, events: list[dict], when: str | None):
    """Moves, adds or removes the Submitted stage to match the date from Edit job.
    A job that skipped Submitted (straight to OA, say) gets the stage added."""
    submitted = next((e for e in events if e["status"] == "Submitted"), None)
    if when is None:
        if submitted:
            supabase.table("status_events").delete().eq("event_id", submitted["event_id"]).execute()
    elif submitted:
        supabase.table("status_events").update({"happened_at": when}).eq("event_id", submitted["event_id"]).execute()
    else:
        supabase.table("status_events").insert({
            "tracking_id": tracking_id, "user_id": uid, "status": "Submitted", "happened_at": when,
        }).execute()

class EditJobBody(ManualJobBody):
    # Your application, not the job posting. Only changed when the form sends it
    # (it does when the date was edited): "YYYY-MM-DD", or null to clear it.
    submitted_on: str | None = None

@app.patch("/api/tracker/{tracking_id}/edit")
def edit_tracked_job(tracking_id: int, body: EditJobBody):
    uid = get_current_user_id()
    row = (
        supabase.table("user_job_tracking")
        .select("tracking_id, status, jobs(*), status_events(*)")
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .single()
        .execute()
    )
    base = editable_fields(row.data["jobs"] or {})
    submitted = {
        "company": body.company.strip(),
        "title": body.title.strip(),
        "location": (body.location or "").strip(),
        "duration": (body.duration or "").strip(),
        "min_duration_months": body.min_duration_months,
        "deadline": (body.deadline or "").strip(),
        "apply_link": (body.apply_link or "").strip(),
        "skills": body.skills,
        "description": (body.description or "").strip(),
    }
    # Keep only the fields that differ from the shared job row
    overrides = {}
    for field, column in FIELD_TO_COLUMN.items():
        if submitted[field] != base[field]:
            value = submitted[field]
            overrides[column] = None if value in ("", [], None) else value

    # Checked before anything is saved, so a bad date leaves the job untouched
    when = None
    if "submitted_on" in body.model_fields_set:
        when = submitted_at_from_date(body.submitted_on, row.data.get("status") or "", datetime.now(timezone.utc).date())
    supabase.table("user_job_tracking").update({"overrides": overrides}).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
    if "submitted_on" in body.model_fields_set:
        set_submitted_date(uid, tracking_id, row.data.get("status_events") or [], when)
    return {"status": "ok"}


# ---------- Add job from URL ----------

GEMINI_MODEL = "gemini-3.5-flash-lite"
MAX_PAGE_BYTES = 2_000_000   # stop downloading after ~2 MB
MIN_TEXT_CHARS = 300         # less text than this = JS-rendered page or login wall
MAX_TEXT_CHARS = 12000       # cap on text sent to Gemini and stored as description
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


class NeedsManualEntry(Exception):
    """Raised when we can't read the page. The frontend then opens the manual form."""


def check_url_is_safe(url: str) -> None:
    # The backend fetches whatever link it is given, so refuse anything that
    # isn't a normal public website (localhost, private network addresses).
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise NeedsManualEntry("That doesn't look like a valid http(s) link.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise NeedsManualEntry("Couldn't find that website.")
    for info in addresses:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise NeedsManualEntry("That link points to a private address.")


def fetch_page(url: str) -> str:
    check_url_is_safe(url)
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=10, stream=True)
    except requests.RequestException:
        raise NeedsManualEntry("Couldn't reach that page.")
    check_url_is_safe(resp.url)  # re-check in case the link redirected somewhere else
    if resp.status_code >= 400:
        raise NeedsManualEntry(f"The site refused the request (status {resp.status_code}).")
    chunks, size = [], 0
    for chunk in resp.iter_content(65536):
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_PAGE_BYTES:
            break
    return b"".join(chunks).decode("utf-8", errors="ignore")

# From URL
# --- Tier 1: schema.org JobPosting data embedded in the page ---

def iter_jsonld_items(data):
    # JSON-LD can be one object, a list, or wrapped in an "@graph" list
    if isinstance(data, list):
        for item in data:
            yield from iter_jsonld_items(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from iter_jsonld_items(data["@graph"])


def is_job_posting(item: dict) -> bool:
    t = item.get("@type")
    return t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t)


def find_job_posting(soup) -> dict | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.get_text())
        except ValueError:
            continue
        for item in iter_jsonld_items(data):
            if is_job_posting(item):
                return item
    return None


def html_to_text(html: str | None) -> str:
    return BeautifulSoup(unescape(html or ""), "html.parser").get_text("\n", strip=True)


def fields_from_jsonld(posting: dict) -> dict:
    org = posting.get("hiringOrganization")
    company = org.get("name") if isinstance(org, dict) else org

    loc = posting.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    address = loc.get("address") if isinstance(loc, dict) else None
    location = None
    if isinstance(address, dict):
        country = address.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        location = address.get("addressLocality") or country
    elif isinstance(address, str):
        location = address

    valid = posting.get("validThrough")
    deadline = valid[:10] if isinstance(valid, str) and re.match(r"^\d{4}-\d{2}-\d{2}", valid) else None

    return {
        "company": company,
        "title": posting.get("title"),
        "location": location,
        "deadline": deadline,
        "description": html_to_text(posting.get("description"))[:MAX_TEXT_CHARS],
    }

# From URL
# --- Tier 2: page text -> Gemini ---

def page_to_text(soup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)[:MAX_TEXT_CHARS]


def extract_with_gemini(text: str) -> dict:
    prompt = f"""Extract info from this job posting page. Return ONLY a JSON object in this exact shape:

{{
  "company": "string or null - the hiring company",
  "title": "string or null - the job title",
  "location": "string or null - city or country, e.g. Singapore",
  "duration": "string or null - internship length/dates if mentioned",
  "min_duration_months": "integer or null - duration converted to months (e.g. '12-week' -> 3)",
  "skills": ["specific tools/skills mentioned"],
  "deadline": "string or null - application deadline as YYYY-MM-DD, only if explicitly stated"
}}

Use null when something is not stated. Do not guess.

Page text:
{text}
"""
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    data = json.loads(response.text)
    return data if isinstance(data, dict) else {}


def clean_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_date(value) -> str | None:
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    return None


class UrlJobBody(BaseModel):
    url: str
    tab_id: int | None = None


@app.post("/api/jobs/from-url")
def add_job_from_url(body: UrlJobBody):
    uid = get_current_user_id()
    tab_id = target_tab_id(uid, body.tab_id)
    url = body.url.strip()

    try:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")

        # Tier 1: structured JobPosting data, if the page has it
        posting = find_job_posting(soup)
        fields = fields_from_jsonld(posting) if posting else {}

        description = fields.get("description") or page_to_text(soup)
        if posting is None and len(description) < MIN_TEXT_CHARS:
            raise NeedsManualEntry("The page has no readable text (it may need a login or JavaScript).")

        # Tier 2: Gemini reads the text. For tier 1 pages it only adds duration and skills.
        try:
            extracted = extract_with_gemini(description)
        except Exception as e:
            print(f"Gemini extraction failed: {e}")
            extracted = {}

        # Values from the page's own JSON-LD win over Gemini's
        merged = {**extracted, **{k: v for k, v in fields.items() if v}}
        if not merged.get("company") or not merged.get("title"):
            raise NeedsManualEntry("Couldn't find the company and job title on that page.")
    except NeedsManualEntry as e:
        # Tier 3: the frontend opens the manual form with the link prefilled
        raise HTTPException(status_code=422, detail=str(e))

    # Same link pasted by the same user = same job_id, so no duplicate rows
    clean_link = url.split("#")[0].rstrip("/")
    job_id = "manual-" + hashlib.sha1(f"{uid}:{clean_link}".encode()).hexdigest()[:16]

    existing = supabase.table("jobs").select("job_id").eq("job_id", job_id).execute()
    if not existing.data:
        skills = merged.get("skills")
        supabase.table("jobs").insert({
            "job_id": job_id,
            "employer_name": merged["company"],
            "job_title": merged["title"],
            "job_city": merged.get("location"),
            "duration": merged.get("duration"),
            "min_duration_months": clean_int(merged.get("min_duration_months")),
            "application_deadline": clean_date(merged.get("deadline")),
            "job_apply_link": url,
            "job_description": description,
            "skills": [s for s in skills if isinstance(s, str)] if isinstance(skills, list) else [],
            "job_publisher": "Link",
            "enrichment_status": "done",
            "job_posted_at_datetime_utc": datetime.now(timezone.utc).isoformat(),
        }).execute()

    status = track_job_for_user(uid, job_id, tab_id)
    return {"status": status, "job_id": job_id}


# ---------- My CV (master CV) ----------

RESUME_BUCKET = "resumes"
MAX_CV_BYTES = 10 * 1024 * 1024


def tailored_groups(tailored: dict) -> list[dict]:
    """Turns the tailor agent's sections -> entries output into
    [{label, lines: [{text, original}]}] groups for the drawer: one group per CV
    entry that was tailored. `original` is the CV line a rewrite came from, or
    None for results saved before rewrites were paired with their lines."""
    groups = []
    for section in tailored.get("sections", []):
        for entry in section.get("entries", []):
            pairs = entry.get("tailored_pairs")
            if pairs:
                lines = [
                    {"text": p["rewritten"], "original": p.get("original")}
                    for p in pairs
                    if p.get("rewritten")
                ]
            else:
                text = entry.get("tailored_bullets") or ""
                lines = [re.sub(r"^\s*[-•*]\s*", "", line).strip() for line in text.splitlines()]
                lines = [{"text": line, "original": None} for line in lines if line]
            if not lines:
                continue
            heading = (entry.get("heading") or "").strip()
            sub = entry.get("subheading")
            label = f"{heading} — {sub}" if sub else heading
            groups.append({"label": label or section.get("title", ""), "lines": lines})
    return groups


def cv_payload(uid: int) -> dict:
    res = (
        supabase.table("users")
        .select("resume_path, resume_filename, resume_size_kb, resume_updated_at, cv_structure")
        .eq("user_id", uid)
        .execute()
    )
    row = res.data[0] if res.data else {}
    if not row.get("resume_path"):
        return {"exists": False}

    # No download link here: the Download button asks /api/cv/file-link when clicked
    return {
        "exists": True,
        "fileName": row.get("resume_filename") or "cv.pdf",
        "sizeKb": row.get("resume_size_kb"),
        "updatedAt": row.get("resume_updated_at"),
        "structure": row.get("cv_structure"),
    }


@app.get("/api/cv")
def get_cv(request: Request):
    payload = cv_payload(get_current_user_id())
    if is_guest(request) and payload["exists"]:
        # A guest learns that a CV exists, never its contents or a link to the file
        return {
            "exists": True,
            "locked": True,
            **{k: payload[k] for k in ("fileName", "sizeKb", "updatedAt")},
        }
    return payload


@app.get("/api/cv/file")
def get_cv_file(request: Request):
    # The PDF itself, served through the API (same origin as the app) so the
    # My CV page can render it with pdf.js without CORS or signed-URL expiry
    if is_guest(request):
        raise HTTPException(status_code=403, detail="View-only guest mode. Enter the access key to see the CV.")
    uid = get_current_user_id()
    rows = supabase.table("users").select("resume_path").eq("user_id", uid).execute().data
    path = rows[0].get("resume_path") if rows else None
    if not path:
        raise HTTPException(status_code=404, detail="No CV uploaded yet.")
    try:
        contents = supabase.storage.from_(RESUME_BUCKET).download(path)
    except Exception as e:
        print(f"CV download failed: {e}")
        raise HTTPException(status_code=502, detail="Couldn't load your CV from storage.")
    return Response(
        content=contents,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="cv.pdf"', "Cache-Control": "no-store"},
    )


@app.get("/api/cv/file-link")
def get_cv_file_link(request: Request):
    if is_guest(request):
        raise HTTPException(status_code=403, detail="View-only guest mode. Enter the access key to download the CV.")
    uid = get_current_user_id()
    rows = supabase.table("users").select("resume_path").eq("user_id", uid).execute().data
    path = rows[0].get("resume_path") if rows else None
    if not path:
        raise HTTPException(status_code=404, detail="No CV uploaded yet.")
    return fresh_file_link(path)


@app.post("/api/cv")
def upload_master_cv(file: UploadFile = File(...)):
    # Plain def (not async) so the slow Gemini call below runs in a worker thread
    uid = get_current_user_id()
    filename = file.filename or "cv.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    contents = file.file.read()
    if len(contents) > MAX_CV_BYTES:
        raise HTTPException(status_code=400, detail="That file is over 10 MB.")
    if not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That doesn't look like a valid PDF.")

    path = f"{uid}/cv.pdf"
    supabase.storage.from_(RESUME_BUCKET).upload(
        path, contents, {"content-type": "application/pdf", "upsert": "true"}
    )
    supabase.table("users").update({
        "resume_path": path,
        "resume_filename": filename,
        "resume_size_kb": round(len(contents) / 1024),
        "resume_updated_at": datetime.now(timezone.utc).isoformat(),
        "cv_structure": None,  # the old structure belonged to the old file
    }).eq("user_id", uid).execute()

    warning = None
    try:
        structure = extract_cv_structure(contents)
        supabase.table("users").update({"cv_structure": structure}).eq("user_id", uid).execute()
    except Exception as e:
        print(f"CV extraction failed: {e}")
        warning = "Your CV was saved, but reading its text failed. Try uploading it again in a minute."

    payload = cv_payload(uid)
    if warning:
        payload["warning"] = warning
    return payload



# ---------- Search interests ----------

class InterestBody(BaseModel):
    role: str
    country: str
    city: str | None = None

class InterestStatusBody(BaseModel):
    status: str

# Backfills in progress and the ones that failed, keyed by (role, country, city)
# as stored in job_interests (lowercase). Kept in memory: after a server restart
# a never-finished backfill simply shows as "not fetched yet" with a Fetch button.
backfills_running: set[tuple] = set()
backfill_errors: dict[tuple, str] = {}

def pair_key(role: str, country: str, city: str | None) -> tuple:
    return (role.strip().lower(), country.strip().lower(), city.strip().lower() if city else None)

def run_backfill(role: str, country: str, city: str | None):
    # Runs after the response has been sent. It opens its own connection
    # because the request is already finished by the time this executes.
    key = pair_key(role, country, city)
    conn = psycopg2.connect(DATABASE_URL)
    try:
        backfill_new_pair(role, country, city, conn)
        backfill_errors.pop(key, None)
    except Exception as e:
        print(f"Backfill failed for {role} / {city} / {country}: {e}")
        backfill_errors[key] = "The job search failed. Try again in a few minutes."
    finally:
        backfills_running.discard(key)
        conn.close()

def schedule_backfill(background_tasks: BackgroundTasks, role: str, country: str, city: str | None) -> bool:
    key = pair_key(role, country, city)
    if key in backfills_running:
        return False
    backfills_running.add(key)
    backfill_errors.pop(key, None)
    background_tasks.add_task(run_backfill, role, country, city)
    return True

def fetch_state(r: dict) -> str:
    """done | running | failed | pending (never fetched and nothing running)."""
    if r["backfilled"]:
        return "done"
    key = pair_key(r["role"], r["country"], r["city"])
    if key in backfills_running:
        return "running"
    if key in backfill_errors:
        return "failed"
    return "pending"

@app.get("/api/interests")
def list_interests():
    uid = get_current_user_id()
    response = (
        supabase.table("job_interests")
        .select("interest_id, role, country, city, status, backfilled, last_fetched_at")
        .eq("user_id", uid)
        .neq("status", "removed")
        .order("created_at")
        .execute()
    )
    return [
        {
            "id": r["interest_id"],
            "role": r["role"],
            "country": r["country"],
            "city": r["city"],
            "status": r["status"],
            "backfilled": r["backfilled"],
            "fetchState": fetch_state(r),
            "fetchError": backfill_errors.get(pair_key(r["role"], r["country"], r["city"])),
            "lastFetchedAt": r["last_fetched_at"],
        }
        for r in (response.data or [])
    ]

@app.post("/api/interests")
def create_interest(body: InterestBody, background_tasks: BackgroundTasks):
    uid = get_current_user_id()
    role = body.role.strip()
    country = body.country.strip()
    city = (body.city or "").strip() or None

    if not role or not country:
        raise HTTPException(status_code=422, detail="Role and country are required.")
    try:
        pycountry.countries.lookup(country)
    except LookupError:
        raise HTTPException(
            status_code=422,
            detail=f"'{country}' isn't a country name I recognise. Try something like Singapore or Thailand.",
        )

    conn = psycopg2.connect(DATABASE_URL)
    try:
        result = add_interest(uid, role, country, city, conn)
    finally:
        conn.close()

    backfilling = result["pair_is_new"] and schedule_backfill(background_tasks, role, country, city)
    return {"status": "added", "backfilling": backfilling}

@app.patch("/api/interests/{interest_id}")
def update_interest_status(interest_id: int, body: InterestStatusBody, background_tasks: BackgroundTasks):
    uid = get_current_user_id()
    if body.status not in ("active", "paused"):
        raise HTTPException(status_code=422, detail="Status must be 'active' or 'paused'.")
    response = (
        supabase.table("job_interests")
        .update({"status": body.status})
        .eq("interest_id", interest_id)
        .eq("user_id", uid)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Interest not found.")
    # Activating an interest that never got its first deep search (it was paused
    # before it ran, or the run failed) starts that search now. This is also the retry.
    r = response.data[0]
    backfilling = False
    if body.status == "active" and not r["backfilled"]:
        backfilling = schedule_backfill(background_tasks, r["role"], r["country"], r["city"])
    return {"status": body.status, "backfilling": backfilling}

@app.delete("/api/interests/{interest_id}")
def remove_interest_endpoint(interest_id: int):
    uid = get_current_user_id()
    response = (
        supabase.table("job_interests")
        .update({"status": "removed"})
        .eq("interest_id", interest_id)
        .eq("user_id", uid)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Interest not found.")
    return {"status": "removed"}


# ---------- Frontend ----------

# In production the built React app (front-end/dist) is served by this same
# server, so the page and the API share one URL. Mounted last so every /api
# route above takes priority. Locally, without a build, Vite serves the app instead.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "front-end" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")