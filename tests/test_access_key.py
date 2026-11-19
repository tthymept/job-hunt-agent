from fastapi.testclient import TestClient

from job_hunt_agent import api

client = TestClient(api.app)


def test_no_key_configured_leaves_api_open(monkeypatch):
    # Local development: APP_ACCESS_KEY unset, so the lock is off.
    # (/api/explore-locations would hit Supabase, so check the middleware via a 404 route.)
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "")
    assert client.get("/api/does-not-exist").status_code == 404


def test_missing_or_wrong_key_is_rejected(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"X-Access-Key": "wrong"}).status_code == 401


def test_right_key_passes_the_lock(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    # Gets past the middleware to the router, which has no such route
    assert client.get("/api/does-not-exist", headers={"X-Access-Key": "secret"}).status_code == 404


def test_guest_can_read_but_not_write(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    guest = {"X-Guest": "1"}
    # Reads get past the middleware to the router, which has no such route
    assert client.get("/api/does-not-exist", headers=guest).status_code == 404
    assert client.post("/api/does-not-exist", headers=guest).status_code == 403
    assert client.patch("/api/does-not-exist", headers=guest).status_code == 403
    assert client.delete("/api/does-not-exist", headers=guest).status_code == 403


def test_guest_sees_only_the_first_tracked_jobs(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    rows = [{"tracking_id": i} for i in range(10)]

    class FakeQuery:
        def __getattr__(self, name):
            return lambda *args, **kwargs: self

        data = rows

    monkeypatch.setattr(api.supabase, "table", lambda name: FakeQuery())
    monkeypatch.setattr(api, "reshape_tracker_row", lambda row, locked=False: {"id": row["tracking_id"]})
    monkeypatch.setattr(api, "load_tabs", lambda uid: [{"tab_id": 7, "name": "My jobs", "enabled": True, "is_default": True}])

    guest = client.get("/api/tracker", headers={"X-Guest": "1"})
    assert [job["id"] for job in guest.json()] == [0, 1, 2, 3]
    assert {job["tabId"] for job in guest.json()} == {7}  # rows without a tab show in the default one
    assert guest.headers["X-Total-Count"] == "5"  # "more exist", not the real total

    owner = client.get("/api/tracker", headers={"X-Access-Key": "secret"})
    assert len(owner.json()) == 10
    assert owner.headers["X-Total-Count"] == "10"


def test_guest_tracker_rows_hide_the_cv_files_and_bullets(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    rows = [{
        "tracking_id": 1,
        "job_id": "job-1",
        "status": "Submitted",
        "my_upload_path": "1/tailored/job-1.pdf",
        "cover_letter_path": "1/cover-letters/job-1.pdf",
        "tailored_cv": '{"sections": [{"entries": [{"heading": "Intern", "tailored_bullets": "- Built it"}]}]}',
        "jobs": {"employer_name": "Acme", "job_title": "Intern"},
    }]

    class FakeQuery:
        def __getattr__(self, name):
            return lambda *args, **kwargs: self

        data = rows

    monkeypatch.setattr(api.supabase, "table", lambda name: FakeQuery())
    monkeypatch.setattr(api, "load_tabs", lambda uid: [{"tab_id": 7, "name": "My jobs", "enabled": True, "is_default": True}])

    [guest] = client.get("/api/tracker", headers={"X-Guest": "1"}).json()
    assert guest["locked"] is True
    assert guest["hasMyUpload"] is False and guest["hasCoverLetter"] is False
    assert guest["bullets"] is None and guest["edit"] is None
    assert guest["co"] == "Acme"  # the job itself still shows

    [owner] = client.get("/api/tracker", headers={"X-Access-Key": "secret"}).json()
    assert owner["hasMyUpload"] is True and owner["hasCoverLetter"] is True
    assert owner["bullets"] == [{"label": "Intern", "lines": [{"text": "Built it", "original": None}]}]
    assert "locked" not in owner
    # Links are made on click, never in the list, so they can't go stale on an open page
    assert not any("url" in key.lower() for key in owner)


def test_file_links_are_made_on_click_and_refused_to_guests(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")

    class FakeQuery:
        def __getattr__(self, name):
            return lambda *args, **kwargs: self

        data = [{"my_upload_path": "1/tailored/job-1.pdf", "cover_letter_path": None, "resume_path": "1/cv.pdf"}]

    class FakeBucket:
        def create_signed_url(self, path, expires_in):
            signed.append((path, expires_in))
            return {"signedURL": f"https://signed/{path}"}

    signed = []
    monkeypatch.setattr(api.supabase, "table", lambda name: FakeQuery())
    monkeypatch.setattr(api.supabase.storage, "from_", lambda bucket: FakeBucket())
    owner = {"X-Access-Key": "secret"}

    res = client.get("/api/tracker/1/file-link?kind=cv", headers=owner)
    assert res.json() == {"url": "https://signed/1/tailored/job-1.pdf"}
    assert signed == [("1/tailored/job-1.pdf", api.FILE_LINK_SECONDS)]
    assert client.get("/api/tracker/1/file-link?kind=cover_letter", headers=owner).status_code == 404
    assert client.get("/api/cv/file-link", headers=owner).json() == {"url": "https://signed/1/cv.pdf"}

    guest = {"X-Guest": "1"}
    assert client.get("/api/tracker/1/file-link?kind=cv", headers=guest).status_code == 403
    assert client.get("/api/cv/file-link", headers=guest).status_code == 403


def test_guest_does_not_see_the_email(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")

    class FakeQuery:
        def __getattr__(self, name):
            return lambda *args, **kwargs: self

        data = [{"name": "Thyme", "email": "me@example.com"}]

    monkeypatch.setattr(api.supabase, "table", lambda name: FakeQuery())
    assert client.get("/api/me", headers={"X-Guest": "1"}).json() == {"name": "Thyme", "email": ""}
    assert client.get("/api/me", headers={"X-Access-Key": "secret"}).json()["email"] == "me@example.com"


def test_unknown_status_is_refused(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "")
    res = client.patch("/api/tracker/1/status", json={"status": "Hired!!"})
    assert res.status_code == 400


def test_guest_cannot_see_the_cv(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    full = {
        "exists": True,
        "fileName": "cv.pdf",
        "sizeKb": 107,
        "updatedAt": "2026-10-12T00:00:00+00:00",
        "structure": {"sections": [{"title": "Education"}]},
    }
    monkeypatch.setattr(api, "cv_payload", lambda uid: full)

    guest = client.get("/api/cv", headers={"X-Guest": "1"}).json()
    assert guest["locked"] is True
    assert "structure" not in guest
    assert client.get("/api/cv/file", headers={"X-Guest": "1"}).status_code == 403

    owner = client.get("/api/cv", headers={"X-Access-Key": "secret"}).json()
    assert owner == full


def test_guest_header_does_not_excuse_a_wrong_key(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    headers = {"X-Guest": "1", "X-Access-Key": "wrong"}
    assert client.get("/api/does-not-exist", headers=headers).status_code == 401


def test_health_check_stays_open_for_render(monkeypatch):
    monkeypatch.setattr(api, "APP_ACCESS_KEY", "secret")
    assert client.get("/api/health").status_code == 200
