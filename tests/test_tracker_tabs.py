import pytest
from fastapi import HTTPException

from job_hunt_agent.api import clean_tab_name, default_tab, free_tab_name, name_taken, new_positions, pick_target_tab, tabs_payload


def tab(tab_id, enabled=True, is_default=False, name="Tab"):
    return {"tab_id": tab_id, "name": name, "enabled": enabled, "is_default": is_default}


def test_default_is_the_flagged_tab():
    tabs = [tab(1), tab(2, is_default=True)]
    assert default_tab(tabs)["tab_id"] == 2


def test_default_falls_back_to_the_oldest_tab():
    assert default_tab([tab(1), tab(2)])["tab_id"] == 1
    assert default_tab([]) is None


def test_only_one_tab_takes_the_job_without_asking():
    assert pick_target_tab([tab(1, is_default=True)], None)["tab_id"] == 1


def test_no_tab_requested_uses_the_default():
    tabs = [tab(1), tab(2, is_default=True), tab(3)]
    assert pick_target_tab(tabs, None)["tab_id"] == 2


def test_disabled_default_is_skipped_for_the_first_enabled_tab():
    tabs = [tab(1, enabled=False, is_default=True), tab(2, enabled=False), tab(3)]
    assert pick_target_tab(tabs, None)["tab_id"] == 3


def test_requested_tab_is_used():
    tabs = [tab(1, is_default=True), tab(2)]
    assert pick_target_tab(tabs, 2)["tab_id"] == 2


def test_requested_tab_must_exist():
    with pytest.raises(ValueError):
        pick_target_tab([tab(1)], 99)


def test_disabled_tab_refuses_new_jobs():
    tabs = [tab(1), tab(2, enabled=False)]
    with pytest.raises(ValueError):
        pick_target_tab(tabs, 2)


def test_all_tabs_disabled_refuses_new_jobs():
    with pytest.raises(ValueError):
        pick_target_tab([tab(1, enabled=False)], None)


def test_payload_marks_exactly_one_default():
    payload = tabs_payload([tab(1, name="2027"), tab(2, name="2028")])
    assert payload == [
        {"id": 1, "name": "2027", "enabled": True, "isDefault": True},
        {"id": 2, "name": "2028", "enabled": True, "isDefault": False},
    ]


def test_tab_name_is_trimmed_and_collapsed():
    assert clean_tab_name("  Internships   2027 ") == "Internships 2027"


def test_tab_name_cannot_be_empty_or_too_long():
    with pytest.raises(HTTPException):
        clean_tab_name("   ")
    with pytest.raises(HTTPException):
        clean_tab_name("x" * 41)


def test_two_tabs_cannot_share_a_name():
    tabs = [tab(1, name="Intern 2027"), tab(2, name="Intern 2028")]
    assert name_taken(tabs, "Intern 2028")
    assert name_taken(tabs, "intern 2028")  # case does not make it a different name
    assert not name_taken(tabs, "Intern 2029")


def test_a_tab_can_keep_its_own_name_when_renamed():
    tabs = [tab(1, name="Intern 2027"), tab(2, name="Intern 2028")]
    assert not name_taken(tabs, "INTERN 2028", except_id=2)
    assert name_taken(tabs, "Intern 2027", except_id=2)


def test_duplicate_name_is_refused_with_a_message():
    tabs = [tab(1, name="Intern 2027")]
    with pytest.raises(HTTPException) as refused:
        free_tab_name(tabs, "  intern   2027 ")
    assert refused.value.status_code == 400
    assert free_tab_name(tabs, " Intern  2028 ") == "Intern 2028"


def test_new_order_follows_the_request():
    assert new_positions([1, 2, 3], [3, 1, 2]) == {3: 1, 1: 2, 2: 3}


def test_jobs_left_out_of_the_order_keep_their_place_below():
    # Job 4 was added on another device after the page loaded
    assert new_positions([1, 2, 3, 4], [2, 1, 3]) == {2: 1, 1: 2, 3: 3, 4: 4}


def test_order_ignores_repeated_ids():
    assert new_positions([1, 2], [2, 2, 1]) == {2: 1, 1: 2}


def test_order_refuses_a_job_from_another_tab():
    with pytest.raises(ValueError):
        new_positions([1, 2], [1, 2, 99])
