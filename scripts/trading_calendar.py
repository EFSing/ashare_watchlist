"""A-share trading-calendar boundary used by date-sensitive workflows.

Weekdays are not assumed to be trading days.  Callers can inject an explicit
holiday set/provider in tests and deployments.  The core runtime uses the
``exchange_calendars`` XSHG provider; if that provider is unavailable or
fails, a weekday raises ``CalendarUnavailable`` (fail-safe).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Iterable


class CalendarUnavailable(RuntimeError):
    """Calendar data is unavailable, so a weekday cannot be classified."""


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"invalid date: {value!r}")
    return datetime.strptime(text, "%Y%m%d").date()


class TradingCalendar:
    """Injectable calendar interface with a fail-safe default."""

    def __init__(
        self,
        holidays: Iterable[date | datetime | str] | None = None,
        provider: Callable[[date], bool] | None = None,
    ) -> None:
        self._holidays = None if holidays is None else frozenset(_as_date(x) for x in holidays)
        self._provider = provider

    def is_trading_day(self, value: date | datetime | str) -> bool:
        day = _as_date(value)
        if day.weekday() >= 5:
            return False
        if self._holidays is not None:
            return day not in self._holidays
        if self._provider is not None:
            try:
                return bool(self._provider(day))
            except Exception as exc:  # pragma: no cover - provider-specific
                raise CalendarUnavailable(f"calendar provider failed for {day}: {exc}") from exc
        raise CalendarUnavailable(
            f"no A-share holiday calendar configured for weekday {day}; refusing to assume trading day"
        )


def default_calendar() -> TradingCalendar:
    """Return XSHG calendar when available, otherwise a fail-safe calendar."""

    try:
        import exchange_calendars as xcals

        xshg = xcals.get_calendar("XSHG")

        def provider(day: date) -> bool:
            return bool(xshg.is_session(day))

        return TradingCalendar(provider=provider)
    except Exception:
        return TradingCalendar()


def previous_trading_day(
    value: date | datetime | str,
    calendar: TradingCalendar | None = None,
) -> str:
    """Return the previous A-share session as ``YYYYMMDD``."""

    current = _as_date(value) - timedelta(days=1)
    cal = calendar or default_calendar()
    while True:
        if cal.is_trading_day(current):
            return current.strftime("%Y%m%d")
        current -= timedelta(days=1)


def trading_days_between(
    start: date | datetime | str,
    end: date | datetime | str,
    calendar: TradingCalendar | None = None,
) -> int:
    """Count A-share sessions in the inclusive interval."""

    first, last = _as_date(start), _as_date(end)
    if last < first:
        return 0
    cal = calendar or default_calendar()
    count = 0
    current = first
    while current <= last:
        if cal.is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count
