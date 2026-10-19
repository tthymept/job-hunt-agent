import pytest

from job_hunt_agent.api import (
    NeedsManualEntry,
    check_url_is_safe,
    clean_date,
    editable_fields,
    fields_from_jsonld,
    job_core_fields,
    location_filter,
    pair_key,
    tailored_groups,
)


def test_core_fields_fall_back_to_asap_and_dashes():
    core = job_core_fields({"employer_name": "Grab", "job_title": "Data Intern"})
    assert core["co"] == "Grab"
    assert core["dl"] == "ASAP"
    assert core["dur"] == "—"
    assert core["loc"] == "—"


def test_core_fields_use_country_name_when_no_city():
    assert job_core_fields({"job_country": "SG"})["loc"] == "Singapore"


def test_editable_fields_only_keep_iso_deadlines():
    assert editable_fields({"application_deadline": "2026-11-30"})["deadline"] == "2026-11-30"
    assert editable_fields({"application_deadline": "rolling basis"})["deadline"] == ""


def test_tailored_groups_strip_bullet_markers_and_skip_untouched_entries():
    tailored = {
        "sections": [{
            "title": "EXPERIENCE",
            "entries": [
                {"heading": "Agoda", "subheading": "Data Intern", "tailored_bullets": "- Built pipelines\n• Shipped dashboards\n"},
                {"heading": "Cafe job", "tailored_bullets": None},
            ],
        }]
    }
    assert tailored_groups(tailored) == [
        {"label": "Agoda — Data Intern", "lines": ["Built pipelines", "Shipped dashboards"]}
    ]


def test_location_filter_matches_city_and_country_code():
    assert location_filter("Singapore") == 'job_city.ilike."*singapore*",job_country.eq.SG'


def test_location_filter_city_only_when_not_a_country():
    assert location_filter("bangkok") == 'job_city.ilike."*bangkok*"'


def test_location_filter_strips_characters_that_break_the_query():
    assert location_filter('bang"kok),x.eq.1') == 'job_city.ilike."*bangkokxeq*"'


def test_location_filter_all_means_no_filter():
    assert location_filter("all") is None
    assert location_filter("") is None


def test_pair_key_matches_how_interests_are_stored():
    assert pair_key(" Data Intern ", "Singapore", None) == ("data intern", "singapore", None)
    assert pair_key("x", "Thailand", "Bangkok") == ("x", "thailand", "bangkok")


@pytest.mark.parametrize("url", [
    "ftp://example.com/job",
    "http://127.0.0.1/admin",
    "http://localhost:8000/api/cv",
    "http://192.168.1.10/",
    "http://169.254.169.254/latest/meta-data",
])
def test_unsafe_urls_are_refused(url):
    with pytest.raises(NeedsManualEntry):
        check_url_is_safe(url)


def test_jsonld_fields():
    posting = {
        "@type": "JobPosting",
        "title": "ML Intern",
        "hiringOrganization": {"name": "Shopee"},
        "jobLocation": {"address": {"addressLocality": "Singapore"}},
        "validThrough": "2026-12-01T00:00:00Z",
        "description": "<p>Build <b>models</b></p>",
    }
    fields = fields_from_jsonld(posting)
    assert fields["company"] == "Shopee"
    assert fields["location"] == "Singapore"
    assert fields["deadline"] == "2026-12-01"
    assert fields["description"] == "Build\nmodels"


def test_clean_date():
    assert clean_date("2026-12-01") == "2026-12-01"
    assert clean_date("1 Dec 2026") is None
