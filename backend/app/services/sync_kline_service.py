"""K-line sync service (P1-06).

Legacy Baostock path. It only persists unadjusted prices.

- Callers own the baostock session and DB session lifetimes.
- Task log written per run, keyed by (task_type, task_key=YYYY-MM-DD:START:END:FLAGS).
- Idempotent: re-runs update `k_line_daily` raw facts in place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.baostock_adapter import (
    ADJUST_RAW,
    fetch_kline,
    reconnect,
)
from app.adapters.baostock_types import KLinePriceGroup
from app.core.errors import AdapterConnectionError, AdapterError, AdapterQuotaExceededError
from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow

logger = logging.getLogger(__name__)


TASK_KLINE = "SYNC_KLINE"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"

AdjustMode = str
_ALL_FLAGS: list[AdjustMode] = ["raw"]


@dataclass(frozen=True)
class KLineSyncResult:
    task_type: str
    task_key: str
    status: str
    expected_count: int      # unique stocks requested
    success_count: int       # stocks with at least one row returned
    missing_count: int       # stocks with no rows returned for any requested flag
    error_count: int         # stocks that raised at least one exception
    rows_written: int
    adjust_flags: list[AdjustMode]
    error_summary: dict[str, object]


def _bs_code_from_ts(ts_code: str) -> str:
    num, market = ts_code.split(".", 1)
    return f"{market.lower()}.{num}"


def _index_by_date(rows: list[KLinePriceGroup]) -> dict[date, KLinePriceGroup]:
    return {r.trade_date: r for r in rows}


def _merge_one_stock(
    raw_rows: list[KLinePriceGroup] | None,
    qfq_rows: list[KLinePriceGroup] | None = None,
    hfq_rows: list[KLinePriceGroup] | None = None,
) -> list[KLineRow]:
    """Map raw legacy rows; adjusted arguments are ignored."""
    _ = qfq_rows, hfq_rows
    raw = _index_by_date(raw_rows) if raw_rows is not None else {}

    merged: list[KLineRow] = []
    for d in sorted(raw):
        anchor = raw.get(d)
        assert anchor is not None
        merged.append(
            KLineRow(
                ts_code=anchor.ts_code,
                trade_date=d,
                trade_status=anchor.trade_status,
                is_st_row=anchor.is_st,
                open_raw=_price(anchor, "open"),
                high_raw=_price(anchor, "high"),
                low_raw=_price(anchor, "low"),
                close_raw=_price(anchor, "close"),
                preclose_raw=_price(anchor, "preclose"),
                volume=anchor.volume,
                amount=anchor.amount,
                turn=anchor.turn,
                pct_chg=anchor.pct_chg,
            )
        )
    return merged


def _price(group: KLinePriceGroup | None, field: str) -> Decimal | None:
    if group is None:
        return None
    return getattr(group, field)


def sync_kline_for_stocks(
    ts_codes: list[str],
    start_date: date,
    end_date: date,
    kline_repo: KLineRepo,
    task_repo: TaskLogRepo,
    triggered_by: str,
    adjust_flags: list[AdjustMode] | None = None,
    today: date | None = None,
    session: Session | None = None,
) -> KLineSyncResult:
    """Sync `k_line_daily` for given stocks over [start_date, end_date] inclusive.

    Args:
        adjust_flags: legacy compatibility; only `raw` is accepted.
        session: if provided, will be committed after each flush batch so data is
                 durably written mid-run rather than held in one large transaction.
    Assumes caller is in a `baostock_session` context and holds a DB session.
    """
    flags: list[AdjustMode] = adjust_flags if adjust_flags is not None else _ALL_FLAGS
    if flags != ["raw"]:
        raise ValueError("legacy Baostock sync only supports adjust_flags=['raw']")
    today = today or datetime.now(UTC).date()
    task_key = f"{TASK_KLINE}:{today.isoformat()}:{start_date.isoformat()}:{end_date.isoformat()}"
    if adjust_flags is not None:
        task_key = f"{task_key}:{'+'.join(flags)}"

    task_repo.upsert_by_key(TaskLogRow(
        task_type=TASK_KLINE,
        task_key=task_key,
        status=STATUS_RUNNING,
        created_by=triggered_by,
    ))

    total = len(ts_codes)
    pending: list[KLineRow] = []   # buffer flushed every FLUSH_EVERY stocks
    FLUSH_EVERY = 50
    LOG_EVERY = 10

    error_codes: list[str] = []
    missing_codes: list[str] = []
    success = 0
    rows_written = 0
    quota_exhausted = False

    logger.info(
        "kline sync start: %d stocks | %s→%s | flags=%s",
        total, start_date, end_date, flags,
    )

    for i, ts_code in enumerate(ts_codes, 1):
        bs_code = _bs_code_from_ts(ts_code)
        fetched: dict[AdjustMode, list[KLinePriceGroup] | None] = {"raw": None}
        try:
            fetched = _fetch_one_stock_with_retry(bs_code, start_date, end_date, flags)
        except AdapterQuotaExceededError as exc:
            logger.error("quota exhausted at %s (%d/%d): %s", ts_code, i, total, exc)
            error_codes.append(ts_code)
            quota_exhausted = True
            break
        except AdapterConnectionError as exc:
            logger.warning("connection error after retry at %s (%d/%d): %s", ts_code, i, total, exc)
            error_codes.append(ts_code)
            continue
        except (AdapterError, Exception) as exc:
            logger.warning("fetch failed %s (%d/%d): %s", ts_code, i, total, exc)
            error_codes.append(ts_code)
            continue

        merged = _merge_one_stock(fetched["raw"])
        if not merged:
            missing_codes.append(ts_code)
            logger.debug("no rows returned for %s", ts_code)
            continue

        pending.extend(merged)
        success += 1

        # Flush buffer to DB every FLUSH_EVERY successful stocks
        if success % FLUSH_EVERY == 0:
            written = _upsert_kline_rows(kline_repo, pending, flags)
            rows_written += written
            pending.clear()
            if session is not None:
                session.commit()
            logger.info(
                "progress: %d/%d stocks | +%d rows (total %d written)",
                i, total, written, rows_written,
            )
        elif i % LOG_EVERY == 0:
            logger.info("progress: %d/%d stocks processed", i, total)

    # Flush remaining
    if pending:
        written = _upsert_kline_rows(kline_repo, pending, flags)
        rows_written += written
        pending.clear()

    logger.info(
        "kline sync done: %d OK / %d missing / %d error | %d rows written",
        success, len(missing_codes), len(error_codes), rows_written,
    )

    finished_at = datetime.now(UTC)
    error_summary: dict[str, object] = {
        "errors": error_codes[:20],
        "missing": missing_codes[:20],
    }
    if quota_exhausted:
        error_summary["quota_exhausted"] = True
        status = STATUS_FAILED
    elif error_codes and success == 0:
        status = STATUS_FAILED
    elif error_codes or missing_codes:
        status = STATUS_PARTIAL
    else:
        status = STATUS_SUCCESS

    task_repo.upsert_by_key(TaskLogRow(
        task_type=TASK_KLINE,
        task_key=task_key,
        status=status,
        created_by=triggered_by,
        finished_at=finished_at,
        expected_count=len(ts_codes),
        success_count=success,
        missing_count=len(missing_codes),
        error_count=len(error_codes),
        error_summary=error_summary if (error_codes or missing_codes or quota_exhausted) else None,
    ))

    return KLineSyncResult(
        task_type=TASK_KLINE,
        task_key=task_key,
        status=status,
        expected_count=len(ts_codes),
        success_count=success,
        missing_count=len(missing_codes),
        error_count=len(error_codes),
        rows_written=rows_written,
        adjust_flags=flags,
        error_summary=error_summary,
    )


def _upsert_kline_rows(kline_repo: KLineRepo, rows: list[KLineRow], flags: list[AdjustMode]) -> int:
    _ = flags
    return kline_repo.upsert_many(rows)


def _fetch_one_stock_with_retry(
    bs_code: str,
    start_date: date,
    end_date: date,
    flags: list[AdjustMode],
) -> dict[AdjustMode, list[KLinePriceGroup] | None]:
    try:
        return _fetch_one_stock(bs_code, start_date, end_date, flags)
    except AdapterConnectionError as exc:
        logger.warning("connection lost fetching %s: %s — reconnecting and retrying once", bs_code, exc)
        reconnect()
        logger.info("reconnect OK, retrying %s", bs_code)
        return _fetch_one_stock(bs_code, start_date, end_date, flags)


def _fetch_one_stock(
    bs_code: str,
    start_date: date,
    end_date: date,
    flags: list[AdjustMode],
) -> dict[AdjustMode, list[KLinePriceGroup] | None]:
    fetched: dict[AdjustMode, list[KLinePriceGroup] | None] = {"raw": None}
    for mode in flags:
        if mode != "raw":
            raise ValueError("legacy Baostock sync only supports raw")
        fetched[mode] = fetch_kline(bs_code, start_date, end_date, ADJUST_RAW)
    return fetched


__all__ = [
    "STATUS_FAILED",
    "STATUS_PARTIAL",
    "STATUS_RUNNING",
    "STATUS_SUCCESS",
    "TASK_KLINE",
    "AdjustMode",
    "KLineSyncResult",
    "sync_kline_for_stocks",
]
