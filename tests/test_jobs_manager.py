from datetime import datetime, timezone

from jobs_manager import is_deadline_stale

CUTOFF = datetime(2026, 10, 12, tzinfo=timezone.utc)


def test_past_iso_deadline_is_stale():
    assert is_deadline_stale("2026-10-01", CUTOFF)


def test_future_deadline_is_kept():
    assert not is_deadline_stale("2026-11-30", CUTOFF)


def test_free_text_deadline_is_left_alone():
    assert not is_deadline_stale("rolling basis", CUTOFF)
    assert not is_deadline_stale("ASAP", CUTOFF)


def test_empty_deadline_is_kept():
    assert not is_deadline_stale(None, CUTOFF)
    assert not is_deadline_stale("", CUTOFF)


def test_timezone_aware_deadline():
    assert is_deadline_stale("2026-10-01T23:59:00+08:00", CUTOFF)
