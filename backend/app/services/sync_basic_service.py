"""Sync service for stock_basic + trade_calendar (P1-05).

Idempotent full-refresh:
- `sync_stock_basic()`: pull the full market via baostock, upsert rows into stock_basic
- `sync_trade_calendar(start, end)`: pull calendar for the window, upsert into trade_calendar
- Both wrap themselves in a `data_update_task` row keyed by `task_type + task_key(=YYYY-MM-DD)`,
  so re-running the same day updates the same log entry (RUNNING → SUCCESS / FAILED).

Callers own the DB session and the baostock session lifetimes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.adapters.baostock_adapter import fetch_stock_basic, fetch_trade_cal
from app.adapters.baostock_types import StockBasicRow as AdapterStockBasicRow
from app.adapters.baostock_types import TradeCalRow as AdapterTradeCalRow
from app.core.errors import AdapterError
from app.repositories.stock_repo import StockBasicRepo, StockBasicRow
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow
from app.repositories.trade_cal_repo import TradeCalRepo, TradeCalRow

logger = logging.getLogger(__name__)


TASK_STOCK_BASIC = "SYNC_STOCK_BASIC"
TASK_TRADE_CAL = "SYNC_TRADE_CAL"

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"


@dataclass(frozen=True)
class SyncResult:
    task_type: str
    task_key: str
    status: str
    expected_count: int
    success_count: int
    error_count: int
    error_message: str | None = None


def _to_repo_stock(row: AdapterStockBasicRow, updated_by: str) -> StockBasicRow:
    return StockBasicRow(
        ts_code=row.ts_code,
        bs_code=row.bs_code,
        name=row.name,
        market=row.market,
        list_date=row.list_date,
        delist_date=row.delist_date,
        is_bj=row.is_bj,
        is_common=row.is_common,
        is_st="ST" in row.name.upper(),
        updated_by=updated_by,
    )


def _to_repo_trade_cal(row: AdapterTradeCalRow) -> TradeCalRow:
    return TradeCalRow(cal_date=row.cal_date, is_open=row.is_open)


def sync_stock_basic(
    stock_repo: StockBasicRepo,
    task_repo: TaskLogRepo,
    triggered_by: str,
    today: date | None = None,
) -> SyncResult:
    """Full-refresh stock_basic. Idempotent by (task_type, task_key=YYYY-MM-DD)."""
    today = today or datetime.now(UTC).date()
    task_key = f"{TASK_STOCK_BASIC}:{today.isoformat()}"

    task_repo.upsert_by_key(TaskLogRow(
        task_type=TASK_STOCK_BASIC,
        task_key=task_key,
        status=STATUS_RUNNING,
        created_by=triggered_by,
    ))

    try:
        adapter_rows = fetch_stock_basic()
        repo_rows = [_to_repo_stock(r, updated_by=triggered_by) for r in adapter_rows]
        stock_repo.upsert_many(repo_rows)
    except (AdapterError, Exception) as exc:
        logger.exception("sync_stock_basic failed: %s", exc)
        task_repo.upsert_by_key(TaskLogRow(
            task_type=TASK_STOCK_BASIC,
            task_key=task_key,
            status=STATUS_FAILED,
            created_by=triggered_by,
            finished_at=datetime.now(UTC),
            error_summary={"message": str(exc)},
        ))
        return SyncResult(
            task_type=TASK_STOCK_BASIC,
            task_key=task_key,
            status=STATUS_FAILED,
            expected_count=0,
            success_count=0,
            error_count=1,
            error_message=str(exc),
        )

    total = len(repo_rows)
    task_repo.upsert_by_key(TaskLogRow(
        task_type=TASK_STOCK_BASIC,
        task_key=task_key,
        status=STATUS_SUCCESS,
        created_by=triggered_by,
        finished_at=datetime.now(UTC),
        expected_count=total,
        success_count=total,
        missing_count=0,
        error_count=0,
    ))
    return SyncResult(
        task_type=TASK_STOCK_BASIC,
        task_key=task_key,
        status=STATUS_SUCCESS,
        expected_count=total,
        success_count=total,
        error_count=0,
    )


def _default_calendar_range(today: date) -> tuple[date, date]:
    """Cover 3 previous years plus the rest of next year (per PRD §4.2)."""
    start = date(today.year - 3, 1, 1)
    end = date(today.year + 1, 12, 31)
    return start, end


def sync_trade_calendar(
    trade_cal_repo: TradeCalRepo,
    task_repo: TaskLogRepo,
    triggered_by: str,
    today: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> SyncResult:
    """Full-refresh trade_calendar for [start, end]. Defaults to last 3y + next year."""
    today = today or datetime.now(UTC).date()
    start_date, end_date = (start_date, end_date) if (start_date and end_date) else _default_calendar_range(today)
    task_key = f"{TASK_TRADE_CAL}:{today.isoformat()}"

    task_repo.upsert_by_key(TaskLogRow(
        task_type=TASK_TRADE_CAL,
        task_key=task_key,
        status=STATUS_RUNNING,
        created_by=triggered_by,
    ))

    try:
        adapter_rows = fetch_trade_cal(start_date, end_date)
        repo_rows = [_to_repo_trade_cal(r) for r in adapter_rows]
        trade_cal_repo.upsert_many(repo_rows)
    except (AdapterError, Exception) as exc:
        logger.exception("sync_trade_calendar failed: %s", exc)
        task_repo.upsert_by_key(TaskLogRow(
            task_type=TASK_TRADE_CAL,
            task_key=task_key,
            status=STATUS_FAILED,
            created_by=triggered_by,
            finished_at=datetime.now(UTC),
            error_summary={"message": str(exc), "range": [start_date.isoformat(), end_date.isoformat()]},
        ))
        return SyncResult(
            task_type=TASK_TRADE_CAL,
            task_key=task_key,
            status=STATUS_FAILED,
            expected_count=0,
            success_count=0,
            error_count=1,
            error_message=str(exc),
        )

    expected = (end_date - start_date).days + 1
    total = len(repo_rows)
    task_repo.upsert_by_key(TaskLogRow(
        task_type=TASK_TRADE_CAL,
        task_key=task_key,
        status=STATUS_SUCCESS,
        created_by=triggered_by,
        finished_at=datetime.now(UTC),
        expected_count=expected,
        success_count=total,
        missing_count=max(expected - total, 0),
        error_count=0,
    ))
    return SyncResult(
        task_type=TASK_TRADE_CAL,
        task_key=task_key,
        status=STATUS_SUCCESS,
        expected_count=expected,
        success_count=total,
        error_count=0,
    )


__all__ = [
    "STATUS_FAILED",
    "STATUS_RUNNING",
    "STATUS_SUCCESS",
    "TASK_STOCK_BASIC",
    "TASK_TRADE_CAL",
    "SyncResult",
    "sync_stock_basic",
    "sync_trade_calendar",
]
