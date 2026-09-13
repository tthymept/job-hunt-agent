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
# 2. YOUR DATA — replace these with your real CV bullets and a real job posting
# ---------------------------------------------------------------------------
CV_BULLETS = [
    "Built a data pipeline in Python that cleaned and merged 5 messy CSV sources into one reporting table, cutting manual reporting time by 60%.",
    "Led a team of 3 interns on a university research project analyzing survey data with pandas and matplotlib.",
    "Designed and taught a 6-week intro-to-SQL workshop for 20 classmates.",
    "Wrote automated tests for a Flask web app, raising test coverage from 40% to 85%.",
    "Presented quarterly findings to non-technical stakeholders using Tableau dashboards.",
    "Volunteered as a social media coordinator for a student club, growing Instagram followers by 2,000 in one semester.",
]

JOB_DESCRIPTION = """
We're hiring a Junior Data Analyst intern. You'll help clean and analyze
internal datasets, build dashboards for stakeholders, and support the data
engineering team with basic pipeline maintenance. Python and SQL experience
required. Bonus: experience communicating data insights to non-technical
audiences, and any exposure to automated testing or CI is a plus.
"""

TOP_K = 3  # how many of your bullets to actually send to the model


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
    print("Finding your most relevant CV bullets for this job...")
    top_bullets = retrieve_relevant_bullets(CV_BULLETS, JOB_DESCRIPTION, TOP_K)

    print("\nGenerating tailored suggestions...\n")
    suggestions = generate_tailored_suggestions(top_bullets, JOB_DESCRIPTION)

    print("=" * 70)
    print("TAILORED SUGGESTIONS")
    print("=" * 70)
    print(suggestions)