"""P2-01 — Unit tests for health_calendar_service (fake repos, no DB)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from app.services.health_calendar_service import (
    STATUS_GRAY,
    STATUS_GREEN,
    STATUS_RED,
    STATUS_YELLOW,
    get_calendar,
)


@dataclass
class _CalRow:
    cal_date: date
    is_open: bool


class _FakeTradeCalRepo:
    def __init__(self, is_open_by_date: dict[date, bool]) -> None:
        self._map = is_open_by_date

    def list_range(self, start: date, end: date):
        return [
            _CalRow(cal_date=d, is_open=v)
            for d, v in sorted(self._map.items())
            if start <= d <= end
        ]


class _FakeStockRepo:
    def __init__(self, expected_by_date: dict[date, int], default: int = 0) -> None:
        self._map = expected_by_date
        self._default = default

    def count_active_at(self, day: date) -> int:
        return self._map.get(day, self._default)


class _FakeKLineRepo:
    def __init__(
        self,
        actual_by_date: dict[date, int] | None = None,
        anomaly_dates: set[date] | None = None,
    ) -> None:
        self._actual = actual_by_date or {}
        self._anomaly = anomaly_dates or set()

    def distinct_stock_counts_by_date_range(self, start: date, end: date) -> dict[date, int]:
        return {d: n for d, n in self._actual.items() if start <= d <= end}

    def anomaly_dates_in_range(self, start: date, end: date) -> set[date]:
        return {d for d in self._anomaly if start <= d <= end}


# Jan 2024: Mon 1 → New Year holiday (closed), Tue 2 → trading, ..., Sat/Sun closed.
_JAN2 = date(2024, 1, 2)
_JAN3 = date(2024, 1, 3)
_JAN4 = date(2024, 1, 4)
_JAN5 = date(2024, 1, 5)
_JAN6 = date(2024, 1, 6)  # Sat
_JAN31 = date(2024, 1, 31)


def _make_trading_days(days: list[date]) -> dict[date, bool]:
    """Every date in list_range is present; only the given ones are is_open=True."""
    out: dict[date, bool] = {}
    for i in range(31):
        d = date(2024, 1, i + 1)
        out[d] = d in days
    return out


def test_calendar_covers_every_day_in_month() -> None:
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN2])),
        stock_repo=_FakeStockRepo({_JAN2: 4000}),
        kline_repo=_FakeKLineRepo({_JAN2: 4000}),
    )
    assert r.year == 2024
    assert r.month == 1
    assert len(r.days) == 31  # Jan has 31 days — covers first/last of month


def test_non_trading_day_is_gray_regardless_of_kline_presence() -> None:
    """US-3.2 EARS #6: weekend/holiday returns gray and is excluded from completeness."""
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN2])),
        stock_repo=_FakeStockRepo({}, default=4000),
        # Sat has bogus kline rows — should still be gray, not green
        kline_repo=_FakeKLineRepo({_JAN6: 100}),
    )
    sat = next(d for d in r.days if d.cal_date == _JAN6)
    assert sat.is_open is False
    assert sat.status == STATUS_GRAY
    assert sat.expected == 0


def test_full_coverage_returns_green() -> None:
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN2, _JAN3])),
        stock_repo=_FakeStockRepo({_JAN2: 4000, _JAN3: 4000}),
        kline_repo=_FakeKLineRepo({_JAN2: 4000, _JAN3: 4000}),
    )
    day = next(d for d in r.days if d.cal_date == _JAN2)
    assert day.status == STATUS_GREEN
    assert day.expected == 4000
    assert day.actual == 4000


def test_partial_coverage_returns_yellow() -> None:
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN2])),
        stock_repo=_FakeStockRepo({_JAN2: 4000}),
        kline_repo=_FakeKLineRepo({_JAN2: 3500}),
    )
    day = next(d for d in r.days if d.cal_date == _JAN2)
    assert day.status == STATUS_YELLOW
    assert day.expected == 4000
    assert day.actual == 3500


def test_zero_coverage_returns_red() -> None:
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN2])),
        stock_repo=_FakeStockRepo({_JAN2: 4000}),
        kline_repo=_FakeKLineRepo({}),  # no kline rows on that trading day
    )
    day = next(d for d in r.days if d.cal_date == _JAN2)
    assert day.status == STATUS_RED
    assert day.actual == 0


def test_anomaly_flag_is_independent_of_status() -> None:
    """US-3.2 EARS #5: anomaly icon is a separate flag; a fully-green day can still carry it."""
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN2])),
        stock_repo=_FakeStockRepo({_JAN2: 100}),
        kline_repo=_FakeKLineRepo({_JAN2: 100}, anomaly_dates={_JAN2}),
    )
    day = next(d for d in r.days if d.cal_date == _JAN2)
    assert day.status == STATUS_GREEN
    assert day.has_anomaly is True


def test_zero_expected_universe_returns_gray_not_red() -> None:
    """Very early history: no active listed stocks → don't falsely flag red."""
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN2])),
        stock_repo=_FakeStockRepo({}, default=0),
        kline_repo=_FakeKLineRepo({}),
    )
    day = next(d for d in r.days if d.cal_date == _JAN2)
    assert day.status == STATUS_GRAY


def test_month_boundary_first_and_last_day_present() -> None:
    """Cross-month boundary: Jan 1 and Jan 31 both appear with correct status."""
    r = get_calendar(
        2024, 1,
        trade_cal_repo=_FakeTradeCalRepo(_make_trading_days([_JAN31])),
        stock_repo=_FakeStockRepo({_JAN31: 50}),
        kline_repo=_FakeKLineRepo({_JAN31: 50}),
    )
    dates = [d.cal_date for d in r.days]
    assert dates[0] == date(2024, 1, 1)
    assert dates[-1] == _JAN31
    last = r.days[-1]
    assert last.status == STATUS_GREEN


def test_invalid_month_raises() -> None:
    fake_cal = _FakeTradeCalRepo({})
    fake_stock = _FakeStockRepo({})
    fake_kline = _FakeKLineRepo()
    with pytest.raises(ValueError):
        get_calendar(2024, 13, fake_cal, fake_stock, fake_kline)
