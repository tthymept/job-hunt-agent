import theirstack_agent
from theirstack_agent import source_name, title_patterns, to_job_row, uses_theirstack


def test_thailand_goes_to_theirstack_and_singapore_does_not():
    assert uses_theirstack("thailand") and uses_theirstack(" Thailand ")
    assert not uses_theirstack("singapore")


def test_intern_roles_also_match_internship_titles():
    assert title_patterns(["data science intern"]) == ["data science intern", "data science internship"]
    assert title_patterns(["data science"]) == ["data science"]


def test_patterns_are_cleaned_and_shared():
    patterns = title_patterns(['("ai engineer" or "machine learning engineer")', "data intern", "data intern"])
    assert patterns == ["ai engineer", "machine learning engineer", "data intern", "data internship"]
    assert all("," not in p for p in title_patterns(["data, ai intern"]))  # commas are refused by the API


def test_source_names():
    assert source_name("https://www.linkedin.com/jobs/view/1/") == "LinkedIn"
    assert source_name("https://au.seek.com/job/1") == "JobsDB (SEEK)"
    assert source_name("https://seagatecareers.com/job/1") == "seagatecareers.com"


def test_job_row_uses_the_fields_store_jobs_expects():
    row = to_job_row({
        "id": 956574317,
        "job_title": "Data Analytics Intern",
        "company": "Seagate Technology",
        "url": "https://www.linkedin.com/jobs/view/4491376313/",
        "source_url": "https://www.linkedin.com/jobs/view/4491376313/",
        "final_url": None,
        "short_location": "Nakhon Ratchasima, Nakhon Ratchasima",
        "locations": [{"name": "Nakhon Ratchasima", "type": "city", "country_code": "TH"}],
        "country_code": "TH",
        "date_posted": "2026-11-19",
        "employment_statuses": ["full_time"],
        "description": "About the role",
        "remote": False,
    })
    assert row["job_id"] == "ts-956574317"
    assert row["job_publisher"] == "LinkedIn"
    assert row["job_city"] == "Nakhon Ratchasima" and row["job_country"] == "TH"
    assert row["job_apply_link"] == "https://www.linkedin.com/jobs/view/4491376313/"


class FakeResponse:
    def __init__(self, jobs):
        self.status_code = 200
        self.jobs = jobs

    def json(self):
        return {"data": self.jobs}


def test_search_never_asks_for_more_jobs_than_credits_left(monkeypatch):
    monkeypatch.setenv("THEIRSTACK_API_KEY", "test")
    asked = []

    def fake_post(url, json, headers, timeout):
        asked.append(json["limit"])
        return FakeResponse([{"id": i} for i in range(json["limit"])])  # every page full

    monkeypatch.setattr(theirstack_agent.requests, "post", fake_post)
    jobs = theirstack_agent.search_theirstack(["data intern"], ["TH"], credits_left=60)
    assert len(jobs) == 60 and asked == [25, 25, 10]


def test_search_stops_when_a_page_is_not_full(monkeypatch):
    monkeypatch.setenv("THEIRSTACK_API_KEY", "test")
    pages = iter([[{"id": i} for i in range(25)], [{"id": 99}]])
    monkeypatch.setattr(theirstack_agent.requests, "post", lambda url, json, headers, timeout: FakeResponse(next(pages)))
    assert len(theirstack_agent.search_theirstack(["data intern"], ["TH"], credits_left=180)) == 26


def test_no_credits_left_means_no_request(monkeypatch):
    monkeypatch.setattr(theirstack_agent.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    assert theirstack_agent.search_theirstack(["data intern"], ["TH"], credits_left=0) == []


def test_in_city_reads_tagged_locations_and_location_text():
    bangkok = {"locations": [{"name": "Khlong Toei", "admin1_name": "Bangkok"}], "location": "Khlong Toei, Bangkok"}
    korat = {"locations": [{"name": "Nakhon Ratchasima", "admin1_name": "Nakhon Ratchasima"}], "location": "Nakhon Ratchasima"}
    assert theirstack_agent.in_city(bangkok, "bangkok")
    assert not theirstack_agent.in_city(korat, "Bangkok")


def test_city_search_sends_location_ids(monkeypatch):
    monkeypatch.setenv("THEIRSTACK_API_KEY", "test")
    sent = []

    def fake_post(url, json, headers, timeout):
        sent.append(json)
        return FakeResponse([])

    monkeypatch.setattr(theirstack_agent.requests, "post", fake_post)
    theirstack_agent.search_theirstack(["data intern"], ["TH"], credits_left=50, locations=[1609348, 1609350])
    assert sent[0]["job_location_or"] == [{"id": 1609348}, {"id": 1609350}]


def test_location_ids_keep_exact_name_matches_in_the_country(monkeypatch):
    monkeypatch.setenv("THEIRSTACK_API_KEY", "test")
    catalog = [
        {"id": 1609348, "name": "Bangkok", "country_code": "TH"},
        {"id": 1609350, "name": "Bangkok", "country_code": "TH"},
        {"id": 1619460, "name": "Bangkok Noi", "country_code": "TH"},
    ]

    class Catalog:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": catalog}

    monkeypatch.setattr(theirstack_agent.requests, "get", lambda *a, **k: Catalog())
    assert theirstack_agent.location_ids("bangkok", "TH") == [1609348, 1609350]
