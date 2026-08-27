from datetime import date, datetime

import pytest

from trading_calendar import (
    CalendarUnavailable,
    TradingCalendar,
    default_calendar,
    previous_trading_day,
)


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
