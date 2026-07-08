"""Single-day health-detail service (P2-02).

For a given trading day, compute:
- expected_count : count of active common stocks on that day
- actual_count   : distinct ts_code with a k_line_daily row on that day
- error_count    : count of ts_codes whose row is anomalous
                   (trade_status != 0 AND all three close columns are NULL)
- success_count  : actual_count - error_count
- missing_count  : expected_count - actual_count
- missing_ts_codes / error_ts_codes : capped at MAX_LISTED_CODES for front-end display

Optionally include the latest matching data_update_task summary (if a SYNC_KLINE
task_key `SYNC_KLINE:<today>:<start>:<end>` covers `day`).

If `day` is not a trading day (`trade_calendar.is_open=false` or missing),
raise `NotFoundError` — API layer maps to `NOT_FOUND_TRADING_DAY`.

Read-only service. No DB writes. Callers own the DB session.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.core.errors import NotFoundError
from app.repositories.kline_repo import KLineRepo
from app.repositories.stock_repo import StockBasicRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.repositories.trade_cal_repo import TradeCalRepo

logger = logging.getLogger(__name__)

MAX_LISTED_CODES = 100
TASK_KLINE = "SYNC_KLINE"

# task_key format: "SYNC_KLINE:<today>:<start_date>:<end_date>"
_KLINE_TASK_KEY_RE = re.compile(
    r"^SYNC_KLINE:(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$"
)


@dataclass(frozen=True)
class DayDetail:
    day: date
    expected_count: int
    success_count: int
    missing_count: int
    error_count: int
    missing_ts_codes: list[str] = field(default_factory=list)
    error_ts_codes: list[str] = field(default_factory=list)
    latest_task_status: str | None = None
    latest_task_finished_at: datetime | None = None
    latest_task_error_summary: dict[str, Any] | None = None


def _covers(task_key: str, day: date) -> bool:
    """True iff a SYNC_KLINE task_key's [start, end] window covers `day`."""
    m = _KLINE_TASK_KEY_RE.match(task_key)
    if not m:
        return False
    try:
        start = date.fromisoformat(m.group(2))
        end = date.fromisoformat(m.group(3))
    except ValueError:
        return False
    return start <= day <= end


def get_day_detail(
    day: date,
    trade_cal_repo: TradeCalRepo,
    stock_repo: StockBasicRepo,
    kline_repo: KLineRepo,
    task_repo: TaskLogRepo,
) -> DayDetail:
    """Compute single-day health detail. Raises NotFoundError for non-trading days."""
    if not trade_cal_repo.is_trading_day(day):
        raise NotFoundError(f"not a trading day: {day.isoformat()}")

    active_codes = set(stock_repo.list_active_ts_codes_at(day))
    actual_codes = kline_repo.ts_codes_on(day)
    anomaly_codes = kline_repo.anomaly_ts_codes_on(day)

    missing = sorted(active_codes - actual_codes)
    # Anomalies count only ts_codes that ARE in the actual set (already fetched but bad).
    errors = sorted(anomaly_codes & actual_codes)

    expected = len(active_codes)
    actual = len(actual_codes & active_codes)  # ignore rows for non-active codes
    error_count = len(errors)
    success = max(actual - error_count, 0)
    missing_count = len(missing)

    # Locate the most recent SYNC_KLINE task covering this day (if any).
    latest_status: str | None = None
    latest_finished: datetime | None = None
    latest_summary: dict[str, Any] | None = None
    latest_task = task_repo.latest_by_type(TASK_KLINE)
    if latest_task is not None and latest_task.task_key and _covers(latest_task.task_key, day):
        latest_status = latest_task.status
        latest_finished = latest_task.finished_at
        latest_summary = latest_task.error_summary

    return DayDetail(
        day=day,
        expected_count=expected,
        success_count=success,
        missing_count=missing_count,
        error_count=error_count,
        missing_ts_codes=missing[:MAX_LISTED_CODES],
        error_ts_codes=errors[:MAX_LISTED_CODES],
        latest_task_status=latest_status,
        latest_task_finished_at=latest_finished,
        latest_task_error_summary=latest_summary,
    )


__all__ = [
    "MAX_LISTED_CODES",
    "TASK_KLINE",
    "DayDetail",
    "get_day_detail",
]
