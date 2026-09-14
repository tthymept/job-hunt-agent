"""
cv_extract_agent.py
--------------------
Reads your CV as a PDF and extracts it into a GENERIC hierarchical shape:

    sections -> entries -> bullets

This does NOT assume your CV has exactly "skills / experience / projects."
Whatever section titles your actual CV uses (Skills & Proficiencies,
Internship Experience, Achievements & Leadership, Certifications,
Publications, anything) get preserved as-is, in the order they appear.

Setup:
    uv add google-genai python-dotenv
    (uses the same GEMINI_API_KEY you already have in .env)

Run:
    uv run cv_extract_agent.py
    -> writes cv_structured.json
"""

import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

GEN_MODEL = "gemini-3.6-flash"
CV_PDF_PATH = "cv.pdf"
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

For example:
{
  "skills_sections": [
    {
      "category": "e.g. Technical Skills",
      "bullets": ["Python (PyTorch, pandas, NumPy, PySpark)", "SQL", "..."]
    }
  ],
  "experience": [
    {
      "role": "e.g. Data Engineering Intern",
      "organization": "e.g. EGCO, Thailand",
      "dates": "e.g. May 2026 - July 2026",
      "bullets": ["Redesigned a scalable real-time telemetry pipeline...", "..."]
    }
  ],
  "projects": [
    {
      "name": "e.g. Rabbit Start Quickathon #2",
      "distinction": "e.g. Champion (1st Place)",
      "dates": "e.g. May 2025",
      "bullets": ["Developed an IoT-based solution...", "..."]
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


def extract_cv_structure(pdf_path: str) -> dict:
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    response = client.models.generate_content(
        model=GEN_MODEL,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            EXTRACTION_PROMPT,
        ],
        config=types.GenerateContentConfig(temperature=0.0),  # deterministic -- this is extraction, not creative writing
    )

    raw_text = response.text.strip()

    # Gemini sometimes wraps JSON in ```json fences even when told not to -- strip defensively
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        raw_text = raw_text.replace("json\n", "", 1)

    return json.loads(raw_text)


if __name__ == "__main__":
    print(f"Extracting structure from {CV_PDF_PATH}...")
    structured_cv = extract_cv_structure(CV_PDF_PATH)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(structured_cv, f, indent=2)

    sections = structured_cv.get("sections", [])
    print(f"\nSaved structured CV to {OUTPUT_PATH}")
    print(f"Found {len(sections)} section(s):")
    for section in sections:
        entry_count = len(section.get("entries", []))
        print(f"  - {section.get('title', 'Untitled section')}: {entry_count} entr{'y' if entry_count == 1 else 'ies'}")
