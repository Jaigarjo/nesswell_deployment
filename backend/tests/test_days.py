from datetime import date, datetime, timezone

import pytest

from app.days import is_valid_timezone, logical_day


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_evening_after_midnight_counts_as_previous_day():
    # 01:30 Saturday in Sydney (AEST, UTC+10) -> Friday
    assert logical_day(utc(2026, 6, 5, 15, 30), "Australia/Sydney") == date(2026, 6, 5)


def test_morning_after_cutoff_is_same_day():
    # 07:00 Saturday in Sydney -> Saturday
    assert logical_day(utc(2026, 6, 5, 21, 0), "Australia/Sydney") == date(2026, 6, 6)


def test_exactly_at_cutoff_is_new_day():
    # 04:00 local Madrid (CEST, UTC+2)
    assert logical_day(utc(2026, 7, 1, 2, 0), "Europe/Madrid") == date(2026, 7, 1)


def test_same_instant_differs_by_timezone():
    ts = utc(2026, 3, 10, 20, 0)
    assert logical_day(ts, "Australia/Sydney") == date(2026, 3, 11)  # 07:00 local
    assert logical_day(ts, "America/New_York") == date(2026, 3, 10)  # 16:00 local


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        logical_day(datetime(2026, 1, 1, 12), "UTC")


def test_timezone_validation():
    assert is_valid_timezone("Australia/Sydney")
    assert not is_valid_timezone("Mars/Olympus")
