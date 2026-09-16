"""
tailor_agent.py
----------------
Works on the GENERIC cv_structured.json shape
(sections -> entries -> bullets) produced by cv_extract_agent.py.

Requires:
    cv_structured.json  (run cv_extract_agent.py first)
    job_description.txt

Run:
    uv run tailor_agent.py
"""

import os
import json
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

EMBED_MODEL = "gemini-embedding-001"
GEN_MODEL = "gemini-3.5-flash-lite" #"gemini-3.6-flash"

CV_STRUCTURED_PATH = "cv_structured.json"
JOB_DESCRIPTION_PATH = "job_description.txt"

TOP_BULLETS_PER_ENTRY = 4         # max bullets sent to the model per entry
ENTRY_RELEVANCE_THRESHOLD = 0.45  # below this, an entry is left untouched -- tune based on what you observe


# ---------------------------------------------------------------------------
# LOADING
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
def embed(text: str) -> np.ndarray:
    response = client.models.embed_content(model=EMBED_MODEL, contents=text)
    return np.array(response.embeddings[0].values)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def score_bullets(bullets: list[str], jd_vector: np.ndarray) -> list[tuple[float, str]]:
    """Returns (score, bullet) pairs, sorted highest relevance first."""
    scored = [(cosine_similarity(embed(b), jd_vector), b) for b in bullets]
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
def generate_tailored_bullets(label: str, bullets: list[str], job_description: str) -> str:
    bullets_text = "\n".join(f"- {b}" for b in bullets)

    prompt = f"""You are a career coach tailoring ONE section of a candidate's CV for a specific job.
This section is: {label}

JOB DESCRIPTION:
{job_description}

EXISTING LINES FOR THIS SECTION:
{bullets_text}

Task:
Rewrite these lines to better match the language and priorities of the job
description, without inventing any new facts, numbers, or experience not
already present. Keep each line's original substance intact -- you are
reframing emphasis and wording, not fabricating new results. Keep the tone
professional and concise. Return only the rewritten lines, one per line.
"""

    response = client.models.generate_content(
        model=GEN_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.4),
    )
    return response.text


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
    passing_ascending = sorted(passing, key=lambda pair: pair[0])  # lowest passing score first (sorted)
    bullets_to_tailor = [b for _, b in passing_ascending[:TOP_BULLETS_PER_ENTRY]] # choose first lowest n in the sorted list

    tailored_text = generate_tailored_bullets(label, bullets_to_tailor, job_description)

    return {
        **entry,
        "tailored_bullets": tailored_text,
        "relevance_score": top_score,
        "status": "tailored",
    }


# ---------------------------------------------------------------------------
# MAIN PIPELINE -- walks sections generically, no hardcoded section names
# ---------------------------------------------------------------------------
def tailor_cv(structured_cv: dict, job_description: str) -> dict:
    jd_vector = embed(job_description)

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


if __name__ == "__main__":
    structured_cv = load_structured_cv()
    job_description = load_job_description()

    results = tailor_cv(structured_cv, job_description)
    print_results(results)

    with open("tailored_output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\n\nFull structured result saved to tailored_output.json")