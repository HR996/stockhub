"""K-line sync service (P1-06).

For each stock code, fetches adjust flags (raw / qfq / hfq) from baostock and
merges them into a single `KLineRow` per (ts_code, trade_date). Suspended-day rows are
kept with `trade_status=0` and null prices (baostock returns empty strings there).

- Callers own the baostock session and DB session lifetimes.
- Task log written per run, keyed by (task_type, task_key=YYYY-MM-DD:START:END:FLAGS).
- Idempotent: re-runs update `k_line_daily` in place via partial upsert.
- adjust_flags controls which of ["raw", "qfq", "hfq"] are fetched; None means all three.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.baostock_adapter import (
    ADJUST_HFQ,
    ADJUST_QFQ,
    ADJUST_RAW,
    fetch_kline,
    reconnect,
)
from app.adapters.baostock_types import KLinePriceGroup
from app.core.errors import AdapterConnectionError, AdapterError, AdapterQuotaExceededError
from app.repositories.kline_repo import AdjustMode, KLineRepo, KLineRow
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow

logger = logging.getLogger(__name__)


TASK_KLINE = "SYNC_KLINE"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"

_ALL_FLAGS: list[AdjustMode] = ["raw", "qfq", "hfq"]

# Map AdjustMode → baostock AdjustFlag constant
_BAOSTOCK_FLAG: dict[AdjustMode, str] = {
    "raw": ADJUST_RAW,
    "qfq": ADJUST_QFQ,
    "hfq": ADJUST_HFQ,
}


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
    error_summary: dict[str, list[str]]


def _bs_code_from_ts(ts_code: str) -> str:
    num, market = ts_code.split(".", 1)
    return f"{market.lower()}.{num}"


def _index_by_date(rows: list[KLinePriceGroup]) -> dict[date, KLinePriceGroup]:
    return {r.trade_date: r for r in rows}


def _merge_one_stock(
    raw_rows: list[KLinePriceGroup] | None,
    qfq_rows: list[KLinePriceGroup] | None,
    hfq_rows: list[KLinePriceGroup] | None,
) -> list[KLineRow]:
    """Merge per-adjust-flag responses into unified rows.

    Pass None for a flag that was not fetched this run; those price columns stay
    as None in the resulting KLineRow (repo will leave existing DB values intact).
    """
    raw = _index_by_date(raw_rows) if raw_rows is not None else {}
    qfq = _index_by_date(qfq_rows) if qfq_rows is not None else {}
    hfq = _index_by_date(hfq_rows) if hfq_rows is not None else {}
    all_dates = sorted(set(raw) | set(qfq) | set(hfq))

    merged: list[KLineRow] = []
    for d in all_dates:
        anchor = raw.get(d) or qfq.get(d) or hfq.get(d)
        assert anchor is not None
        r_raw = raw.get(d)
        r_qfq = qfq.get(d)
        r_hfq = hfq.get(d)
        merged.append(
            KLineRow(
                ts_code=anchor.ts_code,
                trade_date=d,
                trade_status=anchor.trade_status,
                is_st_row=anchor.is_st,
                open_raw=_price(r_raw, "open"),
                high_raw=_price(r_raw, "high"),
                low_raw=_price(r_raw, "low"),
                close_raw=_price(r_raw, "close"),
                preclose_raw=_price(r_raw, "preclose"),
                open_qfq=_price(r_qfq, "open"),
                high_qfq=_price(r_qfq, "high"),
                low_qfq=_price(r_qfq, "low"),
                close_qfq=_price(r_qfq, "close"),
                preclose_qfq=_price(r_qfq, "preclose"),
                open_hfq=_price(r_hfq, "open"),
                high_hfq=_price(r_hfq, "high"),
                low_hfq=_price(r_hfq, "low"),
                close_hfq=_price(r_hfq, "close"),
                preclose_hfq=_price(r_hfq, "preclose"),
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
        adjust_flags: which adjust modes to fetch. None means all three ["raw","qfq","hfq"].
                      Pass a subset to fetch only those columns (others left unchanged in DB).
        session: if provided, will be committed after each flush batch so data is
                 durably written mid-run rather than held in one large transaction.
    Assumes caller is in a `baostock_session` context and holds a DB session.
    """
    flags: list[AdjustMode] = adjust_flags if adjust_flags is not None else _ALL_FLAGS
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
        fetched: dict[AdjustMode, list[KLinePriceGroup] | None] = {
            "raw": None, "qfq": None, "hfq": None,
        }
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

        merged = _merge_one_stock(fetched["raw"], fetched["qfq"], fetched["hfq"])
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
    try:
        return kline_repo.upsert_many(rows, adjust_flags=flags)
    except TypeError as exc:
        if "adjust_flags" not in str(exc):
            raise
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
    fetched: dict[AdjustMode, list[KLinePriceGroup] | None] = {
        "raw": None,
        "qfq": None,
        "hfq": None,
    }
    for mode in flags:
        fetched[mode] = fetch_kline(bs_code, start_date, end_date, _BAOSTOCK_FLAG[mode])
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
