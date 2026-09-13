"""
tailor_agent.py
----------------
The first working piece of the job-hunt agent: a mini RAG pipeline.

What it does:
1. Takes your CV (broken into bullet points) and a job description.
2. Embeds every CV bullet + the job description using Gemini's embedding model.
3. Ranks your bullets by how relevant they are to THIS job (cosine similarity).
4. Sends only the most relevant bullets + the job description to Gemini,
   and asks it to generate tailored suggestions.
5. Prints the result to your terminal.

No FastAPI, no frontend, no database yet. Just the core logic.

Setup:
    uv add google-genai numpy python-dotenv
    Create a file called .env in the same folder containing:
        GEMINI_API_KEY=your_key_here
    Get a free key at https://aistudio.google.com/apikey

Run:
    uv run tailor_agent.py
"""

import os
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. SETUP — load your API key and create the client
# ---------------------------------------------------------------------------
load_dotenv()  # reads the .env file and loads GEMINI_API_KEY into the environment
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

EMBED_MODEL = "gemini-embedding-001"
GEN_MODEL = "gemini-3.6-flash"

# ---------------------------------------------------------------------------
# 2. YOUR DATA — now loaded from plain text files instead of hardcoded here
# ---------------------------------------------------------------------------
CV_PATH = "cv.txt"                    # one bullet per line
JOB_DESCRIPTION_PATH = "job_description.txt"  # the full posting, as plain text

TOP_K = 3  # how many of your bullets to actually send to the model


def load_cv_bullets(path: str = CV_PATH) -> list[str]:
    """Reads cv.txt and returns one CV bullet per non-empty line."""
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_job_description(path: str = JOB_DESCRIPTION_PATH) -> str:
    """Reads the full job posting as one block of text."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


# ---------------------------------------------------------------------------
# 3. EMBEDDING — turn text into vectors so we can compare meaning, not just words
# ---------------------------------------------------------------------------
def embed(text: str) -> np.ndarray:
    response = client.models.embed_content(model=EMBED_MODEL, contents=text)
    return np.array(response.embeddings[0].values)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ---------------------------------------------------------------------------
# 4. RETRIEVAL — find which CV bullets actually matter for THIS job
# ---------------------------------------------------------------------------
def retrieve_relevant_bullets(bullets: list[str], job_description: str, top_k: int) -> list[str]:
    jd_vector = embed(job_description)
    scored = []
    for bullet in bullets:
        bullet_vector = embed(bullet)
        score = cosine_similarity(bullet_vector, jd_vector)
        scored.append((score, bullet))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    print("\n--- Relevance ranking (all bullets, for your own visibility) ---")
    for score, bullet in scored:
        print(f"  {score:.3f}  {bullet[:70]}...")

    return [bullet for _, bullet in scored[:top_k]]


# ---------------------------------------------------------------------------
# 5. GENERATION — ask Gemini to tailor suggestions using only the relevant bullets
# ---------------------------------------------------------------------------
def generate_tailored_suggestions(relevant_bullets: list[str], job_description: str) -> str:
    bullets_text = "\n".join(f"- {b}" for b in relevant_bullets)

    prompt = f"""You are a career coach helping a candidate tailor their CV for one specific job.

JOB DESCRIPTION:
{job_description}

CANDIDATE'S MOST RELEVANT EXISTING CV BULLETS:
{bullets_text}

Task:
For each bullet, rewrite it to more directly match the language and priorities
of the job description, without inventing any new facts or experience.
Then suggest ONE new bullet the candidate should consider adding if they have
related experience not yet listed. Keep the tone professional and concise.
"""

    response = client.models.generate_content(
        model=GEN_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.4),
    )
    return response.text


# ---------------------------------------------------------------------------
# 6. RUN IT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cv_bullets = load_cv_bullets()
    job_description = load_job_description()

    print("Finding your most relevant CV bullets for this job...")
    top_bullets = retrieve_relevant_bullets(cv_bullets, job_description, TOP_K)

    print("\nGenerating tailored suggestions...\n")
    suggestions = generate_tailored_suggestions(top_bullets, job_description)

    print("=" * 70)
    print("TAILORED SUGGESTIONS")
    print("=" * 70)
    print(suggestions)