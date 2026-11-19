"""
tailor_agent.py
----------------
Works on the GENERIC cv_structured.json shape
(sections -> entries -> bullets) produced by cv_extract_agent.py.

Two ways to run:
  1. Standalone/local test: reads cv_structured.json + job_description.txt from disk.
  2. Production path (what the "Update" button calls): fetches the user's
     cv_structure JSONB from `users` and the job's description from `jobs`
     by job_id, tailors it, then writes the result into
     `user_job_tracking.tailored_cv` for that (user_id, job_id) row.

Run standalone:
    uv run tailor_agent.py

Run the DB-backed update for one tracked job:
    uv run tailor_agent.py --user-id 1 --job-id <job_id>
"""

import os
import re
import sys
import json
import argparse
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
DATABASE_URL = os.environ["DATABASE_URL"]  # Neon Postgres connection string

EMBED_MODEL = "gemini-embedding-001"
GEN_MODEL = "gemini-3.5-flash-lite"  # "gemini-3.6-flash"

CV_STRUCTURED_PATH = "cv_structured.json"
JOB_DESCRIPTION_PATH = "job_description.txt"

# The raw JSearch field is usually `job_description` — adjust this if your
# `jobs` table column is named differently.
JOB_DESCRIPTION_COLUMN = "job_description"

TOP_BULLETS_PER_ENTRY = 4         # max bullets sent to the model per entry
ENTRY_RELEVANCE_THRESHOLD = 0.45  # below this, an entry is left untouched -- tune based on what you observe


# ---------------------------------------------------------------------------
# DB ACCESS
# ---------------------------------------------------------------------------
def get_connection():
    return psycopg2.connect(DATABASE_URL)


def fetch_cv_structure(user_id: int) -> dict:
    """Pulls the structured CV JSONB straight from `users`, no local file needed."""
    query = "SELECT cv_structure FROM users WHERE user_id = %s;"
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (user_id,))
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"No user found with user_id={user_id}")
    if row["cv_structure"] is None:
        raise ValueError(f"user_id={user_id} has no cv_structure yet — run cv_extract_agent.py first")

    return row["cv_structure"]  # psycopg2 already deserializes JSONB into a dict


def fetch_job_description(job_id: str) -> str:
    """Pulls the job description text from `jobs` via the job_id that
    user_job_tracking already links to — this is the join the UI relies on."""
    query = f"SELECT {JOB_DESCRIPTION_COLUMN} FROM jobs WHERE job_id = %s;"
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (job_id,))
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"No job found with job_id={job_id}")
    if not row[JOB_DESCRIPTION_COLUMN]:
        raise ValueError(f"job_id={job_id} has an empty {JOB_DESCRIPTION_COLUMN}")

    return row[JOB_DESCRIPTION_COLUMN]


def save_tailored_cv(user_id: int, job_id: str, tailored_result: dict):
    """Writes the tailored result into user_job_tracking.tailored_cv for this
    (user_id, job_id) row. Called once the tailoring finishes."""
    tailored_json = json.dumps(tailored_result)
    now = datetime.now(timezone.utc)

    query = """
        UPDATE user_job_tracking
        SET tailored_cv = %s, status_updated_at = %s
        WHERE user_id = %s AND job_id = %s
        RETURNING tracking_id;
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (tailored_json, now, user_id, job_id))
            row = cur.fetchone()
            conn.commit()

    if row is None:
        raise ValueError(
            f"No user_job_tracking row for user_id={user_id}, job_id={job_id} — "
            "was this job added via 'Add to My Jobs' first?"
        )

    print(f"Saved tailored_cv for tracking_id={row['tracking_id']}")
    return row["tracking_id"]


# ---------------------------------------------------------------------------
# LOCAL FILE LOADING (standalone/dev testing only)
# ---------------------------------------------------------------------------
def load_structured_cv(path: str = CV_STRUCTURED_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_job_description(path: str = JOB_DESCRIPTION_PATH) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ---------------------------------------------------------------------------
# EMBEDDING + SCORING
# ---------------------------------------------------------------------------
EMBED_BATCH_SIZE = 100  # texts per embed_content call (the API's batch limit)

# text -> vector. CV bullets are the same on every run, so after the first
# "Generate" only the job description needs a new embedding. Lives for as
# long as the API process does.
_embedding_cache: dict[str, np.ndarray] = {}


def embed_many(texts: list[str]) -> list[np.ndarray]:
    """Embeds texts in batches, skipping any already in the cache."""
    missing = list(dict.fromkeys(t for t in texts if t not in _embedding_cache))
    for i in range(0, len(missing), EMBED_BATCH_SIZE):
        batch = missing[i:i + EMBED_BATCH_SIZE]
        response = client.models.embed_content(model=EMBED_MODEL, contents=batch)
        for text, embedding in zip(batch, response.embeddings):
            _embedding_cache[text] = np.array(embedding.values)
    return [_embedding_cache[t] for t in texts]


def embed(text: str) -> np.ndarray:
    return embed_many([text])[0]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def score_bullets(bullets: list[str], jd_vector: np.ndarray) -> list[tuple[float, str]]:
    """Returns (score, bullet) pairs, sorted highest relevance first."""
    scored = [(cosine_similarity(v, jd_vector), b) for v, b in zip(embed_many(bullets), bullets)]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored


def entry_label(entry: dict) -> str:
    """Builds a human-readable label from whatever fields this entry actually has."""
    heading = entry.get("heading", "").strip()
    subheading = entry.get("subheading")
    if subheading:
        return f"{heading} — {subheading}"
    return heading


# ---------------------------------------------------------------------------
# GENERATION -- scoped to ONE entry at a time
# ---------------------------------------------------------------------------
def generate_tailored_bullets(label: str, bullets: list[str], job_description: str) -> list[str]:
    """One rewritten line per input line, in the same order, so each rewrite can be
    shown next to its original. Falls back to splitting plain text into lines if
    the model doesn't answer with a JSON list."""
    bullets_text = "\n".join(f"{i}. {b}" for i, b in enumerate(bullets, 1))

    prompt = f"""You are a career coach tailoring ONE section of a candidate's CV for a specific job.
This section is: {label}

JOB DESCRIPTION:
{job_description}

EXISTING LINES FOR THIS SECTION (numbered):
{bullets_text}

Task:
Rewrite each line to better match the language and priorities of the job
description, without inventing any new facts, numbers, or experience not
already present. Keep each line's original substance intact -- you are
reframing emphasis and wording, not fabricating new results. Keep the tone
professional and concise.

Return a JSON array of exactly {len(bullets)} strings: item 1 is the rewrite of
line 1, item 2 of line 2, and so on. Do not merge, split, drop or reorder lines,
and do not include the numbers.
"""

    response = client.models.generate_content(
        model=GEN_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.4, response_mime_type="application/json"),
    )
    text = response.text or ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and all(isinstance(line, str) for line in parsed):
            return [clean_line(line) for line in parsed if clean_line(line)]
    except ValueError:
        pass
    return [clean_line(line) for line in text.splitlines() if clean_line(line)]


def clean_line(line: str) -> str:
    """Drops a leading bullet marker or number ("- ", "• ", "2. ") the model may add."""
    return re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", line).strip()


def pair_rewrites(originals: list[str], rewrites: list[str]) -> list[dict]:
    """[{original, rewritten}] for the drawer. Pairs only when the counts match:
    otherwise there is no telling which rewrite belongs to which line, so the
    rewrites are kept without an original rather than paired wrongly."""
    if len(originals) == len(rewrites):
        return [{"original": o, "rewritten": r} for o, r in zip(originals, rewrites)]
    return [{"original": None, "rewritten": r} for r in rewrites]


# ---------------------------------------------------------------------------
# PER-ENTRY PROCESSING
# ---------------------------------------------------------------------------
def process_entry(entry: dict, jd_vector: np.ndarray, job_description: str) -> dict:
    label = entry_label(entry)
    bullets = entry.get("bullets", [])

    if not bullets:
        return {**entry, "tailored_bullets": None, "relevance_score": 0.0, "status": "no bullets to tailor"}

    scored = score_bullets(bullets, jd_vector)
    top_score = scored[0][0]

    print(f"\n--- {label} (relevance: {top_score:.3f}) ---")
    for score, bullet in scored:
        print(f"  {score:.3f}  {bullet[:70]}...")

    if top_score < ENTRY_RELEVANCE_THRESHOLD:
        return {
            **entry,
            "tailored_bullets": None,
            "relevance_score": top_score,
            "status": "kept as-is (low relevance to this role)",
        }

    # Among bullets that clear the threshold, tailor the WEAKEST-scoring ones first.
    # Reasoning: a bullet that already scores high already reads as relevant to this
    # job -- rewriting it adds little. A bullet that barely clears the bar is relevant
    # in substance but weakly worded for this job, so it benefits most from reframing.
    passing = [pair for pair in scored if pair[0] >= ENTRY_RELEVANCE_THRESHOLD]
    passing_ascending = sorted(passing, key=lambda pair: pair[0])  # lowest passing score first
    bullets_to_tailor = [b for _, b in passing_ascending[:TOP_BULLETS_PER_ENTRY]]

    rewrites = generate_tailored_bullets(label, bullets_to_tailor, job_description)

    return {
        **entry,
        # Plain text, as before, so older readers (print_results) keep working
        "tailored_bullets": "\n".join(rewrites),
        # Each rewrite with the line it came from, for the before/after view
        "tailored_pairs": pair_rewrites(bullets_to_tailor, rewrites),
        "relevance_score": top_score,
        "status": "tailored",
    }


# ---------------------------------------------------------------------------
# MAIN PIPELINE -- walks sections generically, no hardcoded section names
# ---------------------------------------------------------------------------
def tailor_cv(structured_cv: dict, job_description: str) -> dict:
    jd_vector = embed(job_description)
    # Embed every bullet up front in as few calls as possible; the per-entry
    # scoring below then reads them from the cache
    embed_many([
        b
        for section in structured_cv.get("sections", [])
        for entry in section.get("entries", [])
        for b in entry.get("bullets", [])
    ])

    tailored_sections = []
    for section in structured_cv.get("sections", []):
        tailored_entries = [
            process_entry(entry, jd_vector, job_description)
            for entry in section.get("entries", [])
        ]
        tailored_sections.append({
            "title": section.get("title", "Untitled section"),
            "entries": tailored_entries,
        })

    return {"sections": tailored_sections}


def print_results(results: dict) -> None:
    print("\n" + "=" * 70)
    print("TAILORED CV (by section)")
    print("=" * 70)

    for section in results["sections"]:
        print(f"\n{section['title'].upper()}")
        for entry in section["entries"]:
            print(f"\n  {entry_label(entry)}  [{entry['status']}]")
            if entry["tailored_bullets"]:
                print(f"  {entry['tailored_bullets']}")
            else:
                for b in entry.get("bullets", []):
                    print(f"    - {b}")


# ---------------------------------------------------------------------------
# ORCHESTRATOR -- this is what the UI's "Update" button should trigger
# ---------------------------------------------------------------------------
def update_tailored_cv_for_job(user_id: int, job_id: str) -> dict:
    """
    Full DB-backed flow:
      1. fetch this user's structured CV (from `users.cv_structure`)
      2. fetch this job's description (from `jobs`, via the job_id already
         sitting in user_job_tracking)
      3. tailor
      4. write the result into user_job_tracking.tailored_cv
    """
    print(f"Fetching CV structure for user_id={user_id}...")
    structured_cv = fetch_cv_structure(user_id)

    print(f"Fetching job description for job_id={job_id}...")
    job_description = fetch_job_description(job_id)

    print("Tailoring...")
    results = tailor_cv(structured_cv, job_description)
    print_results(results)

    save_tailored_cv(user_id, job_id, results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, help="Run the DB-backed update for this user")
    parser.add_argument("--job-id", type=str, help="Run the DB-backed update for this job")
    args = parser.parse_args()

    if args.user_id and args.job_id:
        # This is the path the "Update" button in the UI calls.
        update_tailored_cv_for_job(args.user_id, args.job_id)
    else:
        # Standalone/dev mode -- local files, no DB writes.
        structured_cv = load_structured_cv()
        job_description = load_job_description()
        results = tailor_cv(structured_cv, job_description)
        print_results(results)

        with open("tailored_output.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print("\n\nFull structured result saved to tailored_output.json")