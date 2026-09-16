import requests, os
from dotenv import load_dotenv
load_dotenv()
HEADERS = {"X-RapidAPI-Key": os.environ["RAPIDAPI_KEY"], "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
URL = "https://jsearch.p.rapidapi.com/search-v2"

"""
test_cases = [
    {"query": "data science intern in bangkok, thailand", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "data science intern in Bangkok", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "data science intern Thailand", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "data scientist intern in Bangkok", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "software engineer intern in Bangkok", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "internship in Bangkok", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "data science intern in Bangkok", "date_posted": "week", "country": "th", "language": "en"},
]
"""

test_cases_2 = [
    {"query": "internship in Bangkok", "date_posted": "month"},                                  # baseline: no country/language at all
    {"query": "internship in Bangkok", "date_posted": "month", "country": "th"},                  # country only, no language override
    {"query": "internship in Thailand", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "jobs in Bangkok", "date_posted": "month", "country": "th", "language": "en"},
    {"query": "internship in Bangkok", "date_posted": "all", "country": "th", "language": "en"},
    {"query": "internship", "date_posted": "month", "country": "th", "language": "en"},
]

for i, params in enumerate(test_cases_2):
    resp = requests.get(URL, headers=HEADERS, params=params)
    data = resp.json()
    jobs = data.get("data", {}).get("jobs", [])
    print(f"[{i}] params={params}")
    print(f"    -> {len(jobs)} jobs, resolved country={data.get('parameters', {}).get('country')}, language={data.get('parameters', {}).get('language')}")