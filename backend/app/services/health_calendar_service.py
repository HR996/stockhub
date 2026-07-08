"""K-line calendar health service (P2-01).

For a given (year, month), classify each calendar day as:
- `gray`  — non-trading day (weekend / holiday / not in trade_calendar or is_open=false)
- `green` — trading day, all active stocks have a k_line_daily row (actual == expected)
- `yellow`— trading day, partial coverage (0 < actual < expected)
- `red`   — trading day, no coverage (actual == 0)

Independently, a day may carry `has_anomaly=True` when at least one k_line_daily
row for that date is non-suspended (`trade_status != 0`) but has ALL three close
columns (close_raw, close_qfq, close_hfq) NULL — meaning no price data at all.
A row with only some adjust-flags populated is NOT an anomaly.

Read-only service. No DB writes. Callers own the DB session.
"""

from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass
from datetime import date

from app.repositories.kline_repo import KLineRepo
from app.repositories.stock_repo import StockBasicRepo
from app.repositories.trade_cal_repo import TradeCalRepo

STATUS_GREEN = "green"
STATUS_YELLOW = "yellow"
STATUS_RED = "red"
STATUS_GRAY = "gray"


@dataclass(frozen=True)
class DayStatus:
    cal_date: date
    is_open: bool
    status: str            # one of STATUS_*
    expected: int          # active common stocks on that day (0 for non-trading)
    actual: int            # distinct ts_code with a k_line_daily row on that day
    has_anomaly: bool      # exists row with trade_status != 0 AND close_raw IS NULL


@dataclass(frozen=True)
class CalendarMonth:
    year: int
    month: int
    days: list[DayStatus]


def _month_range(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, _cal.monthrange(year, month)[1])
    return first, last


def get_calendar(
    year: int,
    month: int,
    trade_cal_repo: TradeCalRepo,
    stock_repo: StockBasicRepo,
    kline_repo: KLineRepo,
) -> CalendarMonth:
    """Build the health calendar for the given month."""
    if not (1 <= month <= 12):
        raise ValueError(f"month out of range: {month}")

    first, last = _month_range(year, month)

    # trade_calendar rows for the month → {date: is_open}
    cal_rows = trade_cal_repo.list_range(first, last)
    is_open_by_date = {row.cal_date: bool(row.is_open) for row in cal_rows}

    # k_line_daily aggregates for the month (both queries scoped to month range)
    actual_by_date = kline_repo.distinct_stock_counts_by_date_range(first, last)
    anomaly_dates = kline_repo.anomaly_dates_in_range(first, last)

    days: list[DayStatus] = []
    total_days = (last - first).days + 1
    for offset in range(total_days):
        d = date.fromordinal(first.toordinal() + offset)
        is_open = is_open_by_date.get(d, False)
        has_anomaly = d in anomaly_dates

        if not is_open:
            days.append(DayStatus(
                cal_date=d, is_open=False, status=STATUS_GRAY,
                expected=0, actual=0, has_anomaly=has_anomaly,
            ))
            continue

        expected = stock_repo.count_active_at(d)
        actual = int(actual_by_date.get(d, 0))
        if expected == 0:
            # No active universe (extremely early history) — treat as gray to avoid false red
            status = STATUS_GRAY
        elif actual == 0:
            status = STATUS_RED
        elif actual < expected:
            status = STATUS_YELLOW
        else:
            status = STATUS_GREEN
        days.append(DayStatus(
            cal_date=d, is_open=True, status=status,
            expected=expected, actual=actual, has_anomaly=has_anomaly,
        ))

    return CalendarMonth(year=year, month=month, days=days)


__all__ = [
    "STATUS_GRAY",
    "STATUS_GREEN",
    "STATUS_RED",
    "STATUS_YELLOW",
    "CalendarMonth",
    "DayStatus",
    "get_calendar",
]
