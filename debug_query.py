import requests
import os
from dotenv import load_dotenv
load_dotenv()

HEADERS = {
    "X-RapidAPI-Key": os.environ["RAPIDAPI_KEY"],
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}
URL = "https://jsearch.p.rapidapi.com/search-v2"

test_cases = [
    {"query": "data scientist intern in Singapore", "date_posted": "week"}, # Found 0
    {"query": "data scientist intern in Singapore", "date_posted": "week", "country": "sg"}, # Found 10 **********
    {"query": "data scientist intern", "date_posted": "week", "country": "sg"}, # Found 0
    {"query": "data scientist intern in Bangkok, Thailand", "date_posted": "week"}, # Found 0
    {"query": "data scientist intern in Bangkok, Thailand", "date_posted": "week", "country": "th"}, # Found 0
    {"query": "data scientist intern", "date_posted": "week", "country": "th"}, # Found 0
]

for i, params in enumerate(test_cases):
    resp = requests.get(URL, headers=HEADERS, params=params)
    data = resp.json()
    jobs = data.get("data", {}).get("jobs", [])
    print(f"[{i}] params={params}")
    print(f"    status={resp.status_code}  jobs_found={len(jobs)}")
    if not jobs:
        print(f"    raw response snippet: {str(data)[:300]}")
    print()