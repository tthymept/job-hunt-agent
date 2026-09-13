"""
search_agent.py
----------------
Standalone script: search real job postings using the JSearch API (via RapidAPI).

JSearch aggregates listings surfaced through Google for Jobs, which includes
postings originally published on LinkedIn, Indeed, ZipRecruiter, Glassdoor,
and many company career pages -- pulled through a legitimate, ToS-compliant
route rather than scraping LinkedIn directly (which violates LinkedIn's terms
and has gotten other tools shut down).

Setup:
    uv add requests python-dotenv
    Add to your .env file:
        RAPIDAPI_KEY=your_key_here
    Get a free key:
        1. Sign up at rapidapi.com
        2. Search the API marketplace for "JSearch"
        3. Subscribe to the free plan (no card needed for the free tier)
        4. Copy your key from the "X-RapidAPI-Key" field on the app's dashboard

Run:
    uv run search_agent.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}
print(f"Calling: {JSEARCH_URL} with headers {HEADERS}")

def search_jobs(role: str, location: str, num_pages: int = 1, remote_only: bool = False) -> list[dict]:
    """
    Searches for jobs matching a role + location.
 
    JSearch takes ONE natural-language query string rather than separate
    role/location fields, so we combine them ourselves:
        role="data analyst intern", location="Singapore"
        -> query="data analyst intern in Singapore"
    This mirrors how you'd type a search into Google for Jobs directly.
    """
    query = f"{role} in {location}"
 
    params = {
        "query": query,
        "page": "1",
        "num_pages": str(num_pages),   # each "page" is ~10 results; more pages = more results, more quota used
        "date_posted": "week",          # options: "all", "today", "3days", "week", "month"
    }
    if remote_only:
        params["remote_jobs_only"] = "true"
 
    response = requests.get(JSEARCH_URL, headers=HEADERS, params=params)
    response.raise_for_status()  # raises an error immediately if the key/request is bad, instead of failing silently
 
    data = response.json()
    return data.get("data", {}).get("jobs", [])
 
 
def print_job_summary(jobs: list[dict]) -> None:
    print(f"\nFound {len(jobs)} postings:\n")
    for job in jobs:
        title = job.get("job_title", "Unknown title")
        company = job.get("employer_name", "Unknown company")
        source = job.get("job_publisher", "Unknown source")   # e.g. "LinkedIn", "Indeed"
        link = job.get("job_apply_link", "")
        posted = job.get("job_posted_at", "Unknown date")
 
        print(f"- {title} @ {company}")
        print(f"  Source: {source}  |  Posted: {posted}")
        print(f"  Apply: {link}\n")
        

if __name__ == "__main__":
    # Edit these two lines to search a different field/location
    ROLE = "data scientist intern"
    LOCATION = "Singapore"

    jobs = search_jobs(role=ROLE, location=LOCATION, num_pages=1)
    print_job_summary(jobs)