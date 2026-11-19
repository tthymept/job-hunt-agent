import pytest
from fastapi import HTTPException

from job_hunt_agent.api import clean_scheduled, clean_text, history_payload, plan_status_change, submitted_at_of


def event(event_id, status, at="2026-11-01T12:00:00+00:00", **extra):
    return {"event_id": event_id, "status": status, "happened_at": at, **extra}


# Submitted -> Online Assignment, the most common path so far
PATH = [event(1, "Submitted"), event(2, "Online Assignment")]


def test_a_new_stage_is_added():
    assert plan_status_change(PATH, "Interview Round 1") == ([], True)


def test_first_move_to_submitted_starts_the_history():
    assert plan_status_change([], "Submitted") == ([], True)


def test_picking_an_earlier_stage_again_drops_the_later_ones_and_keeps_its_date():
    # Undoing a mis-click: Submitted keeps its row (and date), OA goes
    assert plan_status_change(PATH, "Submitted") == ([2], False)


def test_a_new_stage_replaces_later_ones():
    rejected = PATH + [event(3, "Rejected")]
    assert plan_status_change(rejected, "Offered") == ([3], True)


def test_going_back_to_saved_clears_the_history():
    assert plan_status_change(PATH, "Saved / Not Applied") == ([1, 2], False)


def test_untracking_leaves_the_history_alone():
    assert plan_status_change(PATH, "Untracked") == ([], False)


def test_choosing_the_current_stage_changes_nothing():
    assert plan_status_change(PATH, "Online Assignment") == ([], False)


def test_history_is_in_pipeline_order_and_hides_notes_from_guests():
    events = [event(9, "Online Assignment", note="HackerRank"), event(4, "Submitted", note="Referred")]
    owner = history_payload(events)
    assert [h["status"] for h in owner] == ["Submitted", "Online Assignment"]
    assert owner[1]["note"] == "HackerRank"
    assert all(h["note"] is None for h in history_payload(events, locked=True))


def test_submitted_date_comes_from_the_submitted_stage():
    assert submitted_at_of(PATH) == "2026-11-01T12:00:00+00:00"
    assert submitted_at_of([event(2, "Online Assignment")]) is None


def test_scheduled_dates_and_times():
    assert clean_scheduled("2026-11-21") == "2026-11-21T12:00:00+00:00"  # OA due date
    assert clean_scheduled("2026-11-21T07:30:00.000Z") == "2026-11-21T07:30:00+00:00"  # interview time
    assert clean_scheduled("") is None
    with pytest.raises(HTTPException):
        clean_scheduled("next Tuesday")


def test_text_is_trimmed_and_limited():
    assert clean_text("  Jane, recruiter  ", 300, "contact") == "Jane, recruiter"
    assert clean_text("   ", 300, "contact") is None
    with pytest.raises(HTTPException):
        clean_text("x" * 301, 300, "contact")
