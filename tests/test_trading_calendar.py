from datetime import date, datetime

import pytest

from trading_calendar import (
    CalendarUnavailable,
    TradingCalendar,
    default_calendar,
    previous_trading_day,
)
from generation_contract import next_execution_date


def test_previous_trading_day_respects_a_share_holiday_boundary():
    calendar = TradingCalendar(holidays={date(2026, 10, 1), date(2026, 10, 2)})

    assert previous_trading_day(datetime(2026, 10, 5), calendar) == "20260930"


def test_unknown_weekday_holiday_is_fail_safe_when_no_calendar_data_exists():
    calendar = TradingCalendar()

    with pytest.raises(CalendarUnavailable):
        calendar.is_trading_day(date(2026, 8, 27))


def test_default_calendar_uses_real_xshg_session_and_holiday():
    calendar = default_calendar()

    assert calendar.is_trading_day(date(2024, 9, 30)) is True
    assert calendar.is_trading_day(date(2024, 10, 1)) is False


def test_default_xshg_provider_covers_2026_sessions_and_holidays():
    calendar = default_calendar()

    assert calendar.is_trading_day(date(2026, 8, 27)) is True
    assert calendar.is_trading_day(date(2026, 8, 28)) is True
    assert calendar.is_trading_day(date(2026, 2, 23)) is False
    assert calendar.is_trading_day(date(2026, 2, 24)) is True
    assert calendar.is_trading_day(date(2026, 9, 25)) is False
    assert calendar.is_trading_day(date(2026, 9, 28)) is True
    assert all(calendar.is_trading_day(date(2026, 10, day)) is False for day in range(1, 8))
    assert calendar.is_trading_day(date(2026, 10, 8)) is True


def test_default_xshg_provider_returns_official_close():
    calendar = default_calendar()

    assert next_execution_date("2026-08-27", calendar) == "2026-08-28"
    assert calendar.session_close(date(2026, 8, 27)).isoformat() == "2026-08-27T15:00:00+08:00"
