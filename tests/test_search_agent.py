from search_agent import batches, dedupe_key, is_internship, is_junk_publisher, select_jobs, source_rank, wants_internships


def job(title, company="Micron Technology", publisher="LinkedIn Singapore", link=None):
    return {
        "job_id": f"{company}-{title}-{publisher}",
        "job_title": title,
        "employer_name": company,
        "job_publisher": publisher,
        "job_apply_link": link or f"https://{publisher.replace(' ', '').lower()}/{title.replace(' ', '-')}",
    }


def test_internship_titles():
    assert is_internship(job("Intern- PIE RAM (Agentic AI)"))
    assert is_internship(job("Data Science Internship"))
    assert is_internship(job("Graduate Trainee, Data"))
    assert not is_internship(job("Senior AI/ML Engineer"))
    assert not is_internship(job("International Data Analyst"))  # "intern" inside a word doesn't count


def test_only_intern_interests_filter_to_internships():
    assert wants_internships("ai engineer intern")
    assert not wants_internships("data science")


def test_blog_and_qa_sites_are_not_job_sites():
    assert is_junk_publisher(job("AI Intern", publisher="Relidevega.blogspot.com"))
    assert not is_junk_publisher(job("AI Intern", publisher="JobLeads"))


def test_the_same_job_on_different_sites_shares_a_key():
    a = job("Data Science Intern", company="Micron Technology, Inc.", publisher="JobLeads")
    b = job("Data Science Intern", company="Micron Technology", publisher="LinkedIn Singapore")
    assert dedupe_key(a) == dedupe_key(b)
    # A generic first word doesn't merge different companies
    assert dedupe_key(job("AI Intern", company="Singapore Airlines")) != dedupe_key(job("AI Intern", company="Singapore Telecommunications"))


def test_company_page_beats_linkedin_beats_boards_beats_reposters():
    ranks = [
        source_rank(job("AI Intern", publisher="Careers At Micron Technology")),
        source_rank(job("AI Intern", publisher="LinkedIn Singapore")),
        source_rank(job("AI Intern", publisher="MyCareersFuture")),
        source_rank(job("AI Intern", publisher="Trabajo.org")),
    ]
    assert ranks == sorted(ranks) and len(set(ranks)) == 4


def test_select_keeps_one_best_copy_of_each_new_internship():
    results = [
        job("Data Science Intern", publisher="Trabajo.org"),
        job("Data Science Intern", publisher="Careers At Micron Technology"),
        job("Senior Data Scientist"),
        job("AI Intern", publisher="Relidevega.blogspot.com"),
    ]
    to_insert, upgrades, skipped = select_jobs(results, "data science intern", stored={})
    assert [j["job_publisher"] for j in to_insert] == ["Careers At Micron Technology"]
    assert upgrades == []
    assert skipped == {"same job from another site": 1, "not an internship": 1, "not a job site": 1}


def test_select_skips_stored_jobs_and_swaps_in_a_better_link():
    stored_copy = job("Data Science Intern", publisher="JobLeads")
    stored = {dedupe_key(stored_copy): stored_copy}
    better = job("Data Science Intern", publisher="LinkedIn Singapore")
    to_insert, upgrades, _ = select_jobs([better], "data science intern", stored)
    assert to_insert == [] and upgrades == [(stored_copy, better)]
    # A worse copy of a stored job is just skipped
    to_insert, upgrades, skipped = select_jobs([job("Data Science Intern", publisher="BeBee")], "data science intern", stored)
    assert to_insert == [] and upgrades == [] and skipped == {"already stored": 1}


def test_batches_fill_up_to_the_job_and_text_limits():
    rows = [(str(i), "x" * 100) for i in range(7)]
    assert [len(b) for b in batches(rows, max_jobs=3, max_chars=10_000)] == [3, 3, 1]
    assert [len(b) for b in batches(rows, max_jobs=25, max_chars=250)] == [2, 2, 2, 1]


def test_batch_results_map_short_refs_back_to_job_ids(monkeypatch):
    import search_agent

    long_id = "V0NRT3FtNDQt" * 30  # JSearch ids are this long
    reply = '[{"ref": "1", "duration": "6 months", "min_duration_months": 6, "skills": ["SQL"], "application_deadline": null},' \
            ' {"ref": 2, "duration": null, "min_duration_months": null, "skills": [], "application_deadline": null},' \
            ' {"ref": "99", "duration": "made up"}]'
    fake = type("M", (), {"generate_content": lambda self, **kw: type("R", (), {"text": reply})()})()
    monkeypatch.setattr(search_agent, "gemini_client", type("C", (), {"models": fake})())

    results = search_agent.extract_job_info_batch([(long_id, "Six month SQL internship"), ("short-id", "")])
    assert set(results) == {long_id, "short-id"}  # an unknown ref is ignored
    assert results[long_id]["min_duration_months"] == 6
