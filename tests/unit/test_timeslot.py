"""agent_core.timeslot 테스트."""
import datetime

from agent_core.timeslot import get_time_slot


def test_weekday_morning_is_class():
    # 2026-05-06은 수요일 → 평일
    t = datetime.datetime(2026, 5, 6, 10, 0, 0)
    assert get_time_slot(t) == "class"


def test_weekday_evening_is_free():
    t = datetime.datetime(2026, 5, 6, 20, 0, 0)
    assert get_time_slot(t) == "free"


def test_weekday_just_before_class_is_free():
    t = datetime.datetime(2026, 5, 6, 8, 59, 0)
    assert get_time_slot(t) == "free"


def test_weekday_18_is_free():
    # 18시 정각은 free (9 <= h < 18)
    t = datetime.datetime(2026, 5, 6, 18, 0, 0)
    assert get_time_slot(t) == "free"


def test_saturday_is_free_even_at_class_time():
    t = datetime.datetime(2026, 5, 9, 10, 0, 0)  # 토요일
    assert get_time_slot(t) == "free"


def test_sunday_is_free():
    t = datetime.datetime(2026, 5, 10, 14, 0, 0)
    assert get_time_slot(t) == "free"


def test_default_uses_now():
    # 인자 없이 호출해도 예외 없음
    assert get_time_slot() in {"class", "free"}
