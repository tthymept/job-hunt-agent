# src/job_hunt_agent/api.py
import os
import json
import uuid
import re
import socket
import ipaddress
import hashlib
from html import unescape
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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
    rows = [r for r in (response.data or []) if not str(r.get("job_id", "")).startswith("manual-")]

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
    overrides = row.get("overrides") or {}
    merged_raw = {**job_raw, **overrides}
    core = job_core_fields(merged_raw)

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
        "edit": editable_fields(merged_raw),
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

@app.patch("/api/tracker/{tracking_id}/edit")
def edit_tracked_job(tracking_id: int, body: ManualJobBody):
    uid = get_current_user_id()
    row = (
        supabase.table("user_job_tracking")
        .select("tracking_id, jobs(*)")
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

    supabase.table("user_job_tracking").update({"overrides": overrides}).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
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


@app.post("/api/jobs/from-url")
def add_job_from_url(body: UrlJobBody):
    uid = get_current_user_id()
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
            "short_description": description[:300],
            "skills": [s for s in skills if isinstance(s, str)] if isinstance(skills, list) else [],
            "job_publisher": "Link",
            "enrichment_status": "done",
            "job_posted_at_datetime_utc": datetime.now(timezone.utc).isoformat(),
        }).execute()

    status = track_job_for_user(uid, job_id)
    return {"status": status, "job_id": job_id}