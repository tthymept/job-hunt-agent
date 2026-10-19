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
from datetime import datetime, timedelta, timezone

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
)

# Single-user lock for the deployed app. When APP_ACCESS_KEY is set, every /api
# request (except the health check) must send it in the X-Access-Key header.
# Locally it is usually unset, so nothing changes during development.
APP_ACCESS_KEY = os.environ.get("APP_ACCESS_KEY", "")

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
            return JSONResponse(status_code=401, content={"detail": "Access key required."})
    return await call_next(request)

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
def get_me():
    uid = get_current_user_id()
    rows = supabase.table("users").select("name, email").eq("user_id", uid).execute().data
    row = rows[0] if rows else {}
    return {"name": row.get("name") or "", "email": row.get("email") or ""}


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
            bullets = tailored_groups(parsed) if "sections" in parsed else None
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

class StatusBody(BaseModel):
    status: str

@app.patch("/api/tracker/{tracking_id}/status")
def update_status(tracking_id: int, body: StatusBody):
    uid = get_current_user_id()
    response = supabase.table("user_job_tracking").update({
        "status": body.status,
        "status_updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    return {"status": "ok"}

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
async def upload_my_cv(tracking_id: int, file: UploadFile = File(...)):
    uid = get_current_user_id()
    rows = (
        supabase.table("user_job_tracking")
        .select("job_id")
        .eq("tracking_id", tracking_id)
        .eq("user_id", uid)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tracked job not found.")
    job_id = rows[0]["job_id"]
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "pdf"
    path = f"{uid}/tailored/{job_id}.{ext}"
    contents = await file.read()
    supabase.storage.from_("resumes").upload(path, contents, {"content-type": file.content_type, "upsert": "true"})
    supabase.table("user_job_tracking").update({"my_upload_path": path}).eq("tracking_id", tracking_id).eq("user_id", uid).execute()
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
            "skills": [s for s in skills if isinstance(s, str)] if isinstance(skills, list) else [],
            "job_publisher": "Link",
            "enrichment_status": "done",
            "job_posted_at_datetime_utc": datetime.now(timezone.utc).isoformat(),
        }).execute()

    status = track_job_for_user(uid, job_id)
    return {"status": status, "job_id": job_id}


# ---------- My CV (master CV) ----------

RESUME_BUCKET = "resumes"
MAX_CV_BYTES = 10 * 1024 * 1024


def tailored_groups(tailored: dict) -> list[dict]:
    """Turns the tailor agent's sections -> entries output into
    [{label, lines}] groups for the drawer: one group per CV entry that was tailored."""
    groups = []
    for section in tailored.get("sections", []):
        for entry in section.get("entries", []):
            text = entry.get("tailored_bullets")
            if not text:
                continue
            lines = [re.sub(r"^\s*[-•*]\s*", "", line).strip() for line in text.splitlines()]
            lines = [line for line in lines if line]
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

    download_url = None
    try:
        signed = supabase.storage.from_(RESUME_BUCKET).create_signed_url(row["resume_path"], 3600)
        download_url = signed.get("signedURL") or signed.get("signed_url")
    except Exception:
        download_url = None

    return {
        "exists": True,
        "fileName": row.get("resume_filename") or "cv.pdf",
        "sizeKb": row.get("resume_size_kb"),
        "updatedAt": row.get("resume_updated_at"),
        "structure": row.get("cv_structure"),
        "downloadUrl": download_url,
    }


@app.get("/api/cv")
def get_cv():
    return cv_payload(get_current_user_id())


@app.get("/api/cv/file")
def get_cv_file():
    # The PDF itself, served through the API (same origin as the app) so the
    # My CV page can render it with pdf.js without CORS or signed-URL expiry
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