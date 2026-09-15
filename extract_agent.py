"""
cv_extract_agent.py
--------------------
Full flow, now split into explicit steps:

    STEP 1: upload_cv()      -> push a local PDF into Supabase Storage, namespaced by user_id
    STEP 2: download_cv()    -> pull those PDF bytes back down for a given user_id
    STEP 3: extract_cv_structure() -> send those bytes to Gemini, get structured JSON back
    STEP 4: save + print summary

Setup:
    uv add google-genai python-dotenv supabase

.env needs:
    GEMINI_API_KEY=...
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY=eyJ...   # service_role key, backend only, never expose

Run:
    uv run cv_extract_agent.py
    -> writes cv_structured.json
"""

import os
import json
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client

load_dotenv()

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# NOTE: run these once against your users table before using the functions below:
#   ALTER TABLE users ADD COLUMN resume_path TEXT;
#   ALTER TABLE users ADD COLUMN cv_structure JSONB;

GEN_MODEL = "gemini-3.5-flash-lite"
BUCKET = "resumes"
LOCAL_CV_PATH = "cv.pdf"        # only used for the one-time upload step
OUTPUT_PATH = "cv_structured.json"

EXTRACTION_PROMPT = """
You are extracting a CV/resume into structured JSON. Preserve the document's
OWN hierarchy and section names -- do not force it into a fixed template.

Return ONLY valid JSON (no markdown fences, no commentary) matching this shape:

{
  "sections": [
    {
      "title": "the section heading exactly as it appears in the CV, e.g. 'Skills & Proficiencies', 'Internship Experience', 'Achievements & Leadership', 'Certifications' -- use whatever this CV actually calls it",
      "entries": [
        {
          "heading": "the primary label for this entry -- e.g. a skill category name like 'Technical Skills', a job title, or a project name",
          "subheading": "secondary detail if present -- e.g. company/organization, or an award/distinction. Use null if there isn't one.",
          "dates": "date range if present, else null",
          "bullets": ["each bullet or skill line, exactly as written in the CV", "..."]
        }
      ]
    }
  ]
}

Rules:
- Walk through the CV top to bottom and create one section object per section you encounter,
  using its own heading and order -- do not assume any fixed list of section names.
- Within a section, group bullets under the correct entry (e.g. all bullets under one specific
  job title belong to that entry, not mixed with another job's bullets).
- For sections like a skills list where there's no natural "role" or "date" (just a category and
  items), set subheading and dates to null and put the category name in heading.
- Do NOT rewrite, summarize, or improve wording -- copy each bullet/line exactly as it appears.
  This is extraction only, not editing.
- If a section has no clear sub-entries (rare), still wrap it as ONE entry with heading set to
  the section title itself and dates/subheading as null.
"""


# ---------- STEP 1: upload a PDF into Supabase Storage + record it in Postgres ----------
def upload_cv(user_id: str, pdf_bytes: bytes, conn) -> str:
    """
    Uploads pdf_bytes into the bucket under {user_id}/cv.pdf, overwriting any previous
    CV for that user (upsert=true -- we only ever keep the latest one per user), then
    points users.resume_path at it so the rest of the app doesn't need to know the
    storage convention.

    pdf_bytes: raw bytes of the PDF. In a web UI this comes from the upload itself
    (e.g. FastAPI's UploadFile.file.read(), or Streamlit's st.file_uploader().read()) --
    not from a local file path anymore.
    """
    storage_path = f"{user_id}/cv.pdf"
    supabase.storage.from_(BUCKET).upload(
        storage_path, pdf_bytes, {"content-type": "application/pdf", "upsert": "true"}
    )
    set_resume_path(user_id, storage_path, conn)
    print(f"[Step 1] Uploaded -> {BUCKET}/{storage_path}, and recorded on users.resume_path")
    return storage_path


# ---------- STEP 2: download those bytes back down for a given user ----------
def download_cv(storage_path: str) -> bytes:
    """Returns raw PDF bytes for a given storage_path (e.g. '{user_id}/cv.pdf')."""
    pdf_bytes = supabase.storage.from_(BUCKET).download(storage_path)
    print(f"[Step 2] Downloaded {BUCKET}/{storage_path} ({len(pdf_bytes)} bytes)")
    return pdf_bytes


# ---------- Postgres helpers: users.resume_path is the source of truth for "which CV is whose" ----------
def set_resume_path(user_id: str, storage_path: str, conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET resume_path = %s WHERE user_id = %s",
            (storage_path, user_id),
        )
    conn.commit()


def get_resume_path(user_id: str, conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT resume_path FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None


def set_cv_structure(user_id: str, structured_cv: dict, conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET cv_structure = %s WHERE user_id = %s",
            (Json(structured_cv), user_id),
        )
    conn.commit()


def get_cv_structure(user_id: str, conn) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT cv_structure FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None  # psycopg2 deserializes JSONB back into a dict automatically


# ---------- STEP 3: send bytes to Gemini for structured extraction ----------
def extract_cv_structure(pdf_bytes: bytes) -> dict:
    response = gemini_client.models.generate_content(
        model=GEN_MODEL,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(temperature=0.0),  # deterministic -- extraction, not creative writing
    )

    raw_text = response.text.strip()

    # Gemini sometimes wraps JSON in ```json fences even when told not to -- strip defensively
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json\n", "", 1)

    print("[Step 3] Extraction complete")
    return json.loads(raw_text)


# ---------- STEP 4: save to Postgres (source of truth) + local JSON (for quick inspection) ----------
def save_structure(user_id: str, structured_cv: dict, conn, output_path: str = OUTPUT_PATH) -> None:
    set_cv_structure(user_id, structured_cv, conn)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structured_cv, f, indent=2)

    sections = structured_cv.get("sections", [])
    print(f"[Step 4] Saved cv_structure to users table (user_id={user_id}) and to {output_path}")
    print(f"Found {len(sections)} section(s):")
    for section in sections:
        entry_count = len(section.get("entries", []))
        print(f"  - {section.get('title', 'Untitled section')}: {entry_count} entr{'y' if entry_count == 1 else 'ies'}")


if __name__ == "__main__":
    test_user_id = 1  # real user_id from the users table

    conn = psycopg2.connect(os.environ["DATABASE_URL"])  # your Neon connection string

    # Local file read here is just standing in for a web upload during testing --
    # in the actual UI, pdf_bytes comes straight from the upload, no disk read needed.
    with open(LOCAL_CV_PATH, "rb") as f:
        local_pdf_bytes = f.read()

    storage_path = upload_cv(test_user_id, local_pdf_bytes, conn)

    # From here on, everything looks up the path via Postgres rather than assuming it --
    # this is exactly what the tailor agent / tracker agent will do later too.
    resume_path = get_resume_path(test_user_id, conn)
    pdf_bytes = download_cv(resume_path)
    structured_cv = extract_cv_structure(pdf_bytes)
    save_structure(test_user_id, structured_cv, conn)

    conn.close()