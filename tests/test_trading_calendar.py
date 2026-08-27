from datetime import date, datetime

import pytest

from trading_calendar import (
    CalendarUnavailable,
    TradingCalendar,
    previous_trading_day,
)


def test_previous_trading_day_respects_a_share_holiday_boundary():
    calendar = TradingCalendar(holidays={date(2026, 10, 1), date(2026, 10, 2)})

    assert previous_trading_day(datetime(2026, 10, 5), calendar) == "20260930"


def test_unknown_weekday_holiday_is_fail_safe_when_no_calendar_data_exists():
    calendar = TradingCalendar()

    with pytest.raises(CalendarUnavailable):
        calendar.is_trading_day(date(2026, 8, 27))

