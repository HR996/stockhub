"""Tushare data pipeline.

The pipeline keeps the existing application tables as the canonical read model:
stock_basic, trade_calendar, k_line_daily, latest_market_cap and sw_industry_*.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.adapters import tushare_adapter
from app.adapters.tushare_types import (
    TushareAdjFactorRow,
    TushareDailyBasicRow,
    TushareDailyRow,
    TushareStockBasicRow,
)
from app.core.errors import AdapterAuthError, AdapterError, AdapterQuotaExceededError
from app.models.stock_basic import StockBasic
from app.repositories.adj_factor_repo import AdjFactorRepo, AdjFactorUpsertRow
from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.market_cap_repo import MarketCapRepo, MarketCapUpsertRow
from app.repositories.qfq_cache_repo import rebuild_qfq_cache
from app.repositories.stock_repo import StockBasicRepo, StockBasicRow
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow
from app.repositories.trade_cal_repo import TradeCalRepo, TradeCalRow

logger = logging.getLogger(__name__)

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"

TASK_TUSHARE_INIT = "TUSHARE_INIT"
TASK_TUSHARE_UPDATE_DAILY = "TUSHARE_UPDATE_DAILY"
TASK_TUSHARE_SYNC_BASIC = "TUSHARE_SYNC_BASIC"
TASK_TUSHARE_SYNC_TRADE_CAL = "TUSHARE_SYNC_TRADE_CAL"
TASK_TUSHARE_QFQ_CACHE = "TUSHARE_QFQ_CACHE"

SOURCE_TUSHARE_DAILY_BASIC = "tushare_daily_basic"
SOURCE_TUSHARE_MISSING = "tushare_missing"

HUNDRED = Decimal("100")
THOUSAND = Decimal("1000")
TEN_THOUSAND = Decimal("10000")


@dataclass(frozen=True)
class PipelineResult:
    task_type: str
    task_key: str
    status: str
    expected_count: int = 0
    success_count: int = 0
    missing_count: int = 0
    error_count: int = 0
    rows_written: int = 0
    error_summary: dict[str, object] | None = None


@dataclass
class TradeDateSyncStats:
    trade_date: date
    daily_rows: int = 0
    daily_basic_rows: int = 0
    adj_factor_rows: int = 0
    suspended_rows: int = 0
    kline_rows_written: int = 0
    market_cap_rows_written: int = 0
    adj_factor_rows_written: int = 0
    affected_ts_codes: set[str] = field(default_factory=set)


def sync_stock_basic_from_tushare(
    pro: object,
    session: Session,
    *,
    triggered_by: str,
    today: date | None = None,
) -> PipelineResult:
    today = today or datetime.now(UTC).date()
    task_key = f"{TASK_TUSHARE_SYNC_BASIC}:{today.isoformat()}"
    task_repo = TaskLogRepo(session)
    _mark_running(task_repo, TASK_TUSHARE_SYNC_BASIC, task_key, triggered_by)
    try:
        rows = [_to_stock_repo_row(row, triggered_by) for row in tushare_adapter.fetch_stock_basic(pro)]
        written = StockBasicRepo(session).upsert_many(rows)
    except (AdapterError, Exception) as exc:
        logger.exception("tushare stock_basic sync failed: %s", exc)
        return _mark_failed(task_repo, TASK_TUSHARE_SYNC_BASIC, task_key, triggered_by, exc)

    _mark_finished(
        task_repo,
        TASK_TUSHARE_SYNC_BASIC,
        task_key,
        triggered_by,
        STATUS_SUCCESS,
        expected_count=len(rows),
        success_count=written,
    )
    return PipelineResult(TASK_TUSHARE_SYNC_BASIC, task_key, STATUS_SUCCESS, len(rows), written, rows_written=written)


def sync_trade_calendar_from_tushare(
    pro: object,
    session: Session,
    *,
    start: date,
    end: date,
    triggered_by: str,
    today: date | None = None,
) -> PipelineResult:
    today = today or datetime.now(UTC).date()
    task_key = f"{TASK_TUSHARE_SYNC_TRADE_CAL}:{today.isoformat()}:{start.isoformat()}:{end.isoformat()}"
    task_repo = TaskLogRepo(session)
    _mark_running(task_repo, TASK_TUSHARE_SYNC_TRADE_CAL, task_key, triggered_by)
    try:
        rows = [
            TradeCalRow(cal_date=row.cal_date, is_open=row.is_open)
            for row in tushare_adapter.fetch_trade_cal(pro, start, end)
        ]
        written = TradeCalRepo(session).upsert_many(rows)
    except (AdapterError, Exception) as exc:
        logger.exception("tushare trade_cal sync failed: %s", exc)
        return _mark_failed(task_repo, TASK_TUSHARE_SYNC_TRADE_CAL, task_key, triggered_by, exc)

    expected = (end - start).days + 1
    _mark_finished(
        task_repo,
        TASK_TUSHARE_SYNC_TRADE_CAL,
        task_key,
        triggered_by,
        STATUS_SUCCESS,
        expected_count=expected,
        success_count=written,
        missing_count=max(expected - written, 0),
    )
    return PipelineResult(TASK_TUSHARE_SYNC_TRADE_CAL, task_key, STATUS_SUCCESS, expected, written, max(expected - written, 0), rows_written=written)


def sync_trade_date_from_tushare(
    pro: object,
    session: Session,
    *,
    trade_date: date,
    triggered_by: str,
    write_task_log: bool = True,
) -> TradeDateSyncStats:
    """Sync daily/daily_basic/adj_factor for one trading date.

    The caller must only call this for open trading days. If any Tushare endpoint
    fails, no suspended placeholder rows are synthesized for the date.
    """
    task_repo = TaskLogRepo(session)
    task_key = f"{TASK_TUSHARE_UPDATE_DAILY}:{trade_date.isoformat()}"
    if write_task_log:
        _mark_running(task_repo, TASK_TUSHARE_UPDATE_DAILY, task_key, triggered_by)

    try:
        daily_rows = tushare_adapter.fetch_daily_by_trade_date(pro, trade_date)
        daily_basic_rows = tushare_adapter.fetch_daily_basic_by_trade_date(pro, trade_date)
        adj_factor_rows = tushare_adapter.fetch_adj_factor_by_trade_date(pro, trade_date)

        stats = _persist_trade_date(
            session,
            trade_date=trade_date,
            daily_rows=daily_rows,
            daily_basic_rows=daily_basic_rows,
            adj_factor_rows=adj_factor_rows,
        )
    except (AdapterError, Exception) as exc:
        logger.exception("tushare daily sync failed for %s: %s", trade_date, exc)
        if write_task_log:
            _mark_failed(task_repo, TASK_TUSHARE_UPDATE_DAILY, task_key, triggered_by, exc)
        raise

    if write_task_log:
        _mark_finished(
            task_repo,
            TASK_TUSHARE_UPDATE_DAILY,
            task_key,
            triggered_by,
            STATUS_SUCCESS,
            expected_count=stats.daily_rows + stats.suspended_rows,
            success_count=stats.kline_rows_written,
            missing_count=stats.suspended_rows,
            error_summary={
                "daily_rows": stats.daily_rows,
                "daily_basic_rows": stats.daily_basic_rows,
                "adj_factor_rows": stats.adj_factor_rows,
                "suspended_rows": stats.suspended_rows,
            },
        )
    return stats


def init_range_from_tushare(
    pro: object,
    session_factory: Callable[[], AbstractContextManager[Session]],
    *,
    start: date,
    end: date,
    triggered_by: str,
    force: bool = False,
) -> PipelineResult:
    """Initialize a range with per-day commits, progress logs and resume."""
    task_key = f"{TASK_TUSHARE_INIT}:{start.isoformat()}:{end.isoformat()}"
    with session_factory() as session:
        _ensure_success(
            sync_stock_basic_from_tushare(
                pro, session, triggered_by=triggered_by, today=end
            )
        )
    with session_factory() as session:
        _ensure_success(
            sync_trade_calendar_from_tushare(
                pro, session, start=start, end=end, triggered_by=triggered_by, today=end
            )
        )
    with session_factory() as session:
        open_days = [
            row.cal_date
            for row in TradeCalRepo(session).list_range(start, end)
            if row.is_open
        ]

    expected = len(open_days)
    errors: list[str] = []
    failed_dates: list[str] = []
    total_written = 0
    succeeded = 0
    skipped = 0
    _write_parent_progress(
        session_factory, task_key, triggered_by, expected, 0, 0, total_written,
        current_date=None, failed_dates=[], cache_status="PENDING",
    )
    try:
        for index, day in enumerate(open_days, start=1):
            child_key = f"{TASK_TUSHARE_UPDATE_DAILY}:{day.isoformat()}"
            with session_factory() as session:
                existing = TaskLogRepo(session).find_by_key(
                    TASK_TUSHARE_UPDATE_DAILY, child_key
                )
            if not force and existing is not None and existing.status == STATUS_SUCCESS:
                skipped += 1
                succeeded += 1
                logger.info("[%d/%d] %s skipped: already committed", index, expected, day)
                _write_parent_progress(
                    session_factory, task_key, triggered_by, expected, succeeded,
                    len(failed_dates), total_written, current_date=day,
                    failed_dates=failed_dates, cache_status="PENDING",
                )
                continue

            logger.info("[%d/%d] %s fetching...", index, expected, day)
            _write_child_status(
                session_factory, child_key, triggered_by, STATUS_RUNNING
            )
            started = time.monotonic()
            try:
                with session_factory() as session:
                    stats = sync_trade_date_from_tushare(
                        pro,
                        session,
                        trade_date=day,
                        triggered_by=triggered_by,
                        write_task_log=True,
                    )
                total_written += stats.kline_rows_written + stats.market_cap_rows_written + stats.adj_factor_rows_written
                succeeded += 1
                logger.info(
                    "[%d/%d] %s committed: daily=%d daily_basic=%d adj_factor=%d elapsed=%.2fs",
                    index, expected, day, stats.daily_rows, stats.daily_basic_rows,
                    stats.adj_factor_rows, time.monotonic() - started,
                )
            except (AdapterAuthError, AdapterQuotaExceededError):
                _write_child_failure(
                    session_factory, child_key, triggered_by, "authentication or quota failure"
                )
                raise
            except AdapterError as exc:
                errors.append(f"{day.isoformat()}: {exc}")
                failed_dates.append(day.isoformat())
                _write_child_failure(
                    session_factory, child_key, triggered_by, str(exc)
                )
                logger.error("[%d/%d] %s failed: %s", index, expected, day, exc)
            _write_parent_progress(
                session_factory, task_key, triggered_by, expected, succeeded,
                len(failed_dates), total_written, current_date=day,
                failed_dates=failed_dates, cache_status="PENDING",
            )

        cache_key = f"{TASK_TUSHARE_QFQ_CACHE}:ALL"
        _write_child_status(
            session_factory, cache_key, triggered_by, STATUS_RUNNING,
            task_type=TASK_TUSHARE_QFQ_CACHE,
        )
        logger.info("building latest-basedate QFQ cache...")
        try:
            with session_factory() as session:
                stocks, cache_rows = rebuild_qfq_cache(session)
                _mark_finished(
                    TaskLogRepo(session), TASK_TUSHARE_QFQ_CACHE, cache_key,
                    triggered_by, STATUS_SUCCESS, expected_count=stocks,
                    success_count=stocks, error_summary={"rows_written": cache_rows},
                )
        except Exception as exc:
            _write_child_failure(
                session_factory, cache_key, triggered_by, str(exc),
                task_type=TASK_TUSHARE_QFQ_CACHE,
            )
            raise
        total_written += cache_rows
        cache_status = STATUS_SUCCESS
        logger.info("QFQ cache committed: stocks=%d rows=%d", stocks, cache_rows)
    except KeyboardInterrupt:
        _finish_parent(
            session_factory, task_key, triggered_by, STATUS_PARTIAL, expected,
            succeeded, len(failed_dates), total_written, failed_dates, "INTERRUPTED",
        )
        raise
    except Exception as exc:
        logger.exception("tushare init stopped: %s", exc)
        _finish_parent(
            session_factory, task_key, triggered_by, STATUS_PARTIAL, expected,
            succeeded, len(failed_dates) + 1, total_written,
            [*failed_dates, str(exc)], "FAILED",
        )
        raise

    status = STATUS_PARTIAL if errors else STATUS_SUCCESS
    _finish_parent(
        session_factory, task_key, triggered_by, status, expected, succeeded,
        len(failed_dates), total_written, failed_dates, cache_status,
    )
    return PipelineResult(
        TASK_TUSHARE_INIT,
        task_key,
        status,
        expected_count=expected,
        success_count=succeeded,
        missing_count=max(expected - succeeded - len(failed_dates), 0),
        error_count=len(failed_dates),
        rows_written=total_written,
        error_summary={
            "errors": errors[:20], "failed_dates": failed_dates[:20],
            "skipped_dates": skipped, "cache_status": cache_status,
        },
    )


def update_one_day_from_tushare(
    pro: object,
    session: Session,
    *,
    trade_date: date,
    triggered_by: str,
) -> PipelineResult:
    stats = sync_trade_date_from_tushare(
        pro,
        session,
        trade_date=trade_date,
        triggered_by=triggered_by,
        write_task_log=True,
    )
    return PipelineResult(
        TASK_TUSHARE_UPDATE_DAILY,
        f"{TASK_TUSHARE_UPDATE_DAILY}:{trade_date.isoformat()}",
        STATUS_SUCCESS,
        expected_count=stats.daily_rows + stats.suspended_rows,
        success_count=stats.kline_rows_written,
        missing_count=stats.suspended_rows,
        rows_written=stats.kline_rows_written + stats.market_cap_rows_written + stats.adj_factor_rows_written,
    )


def _persist_trade_date(
    session: Session,
    *,
    trade_date: date,
    daily_rows: list[TushareDailyRow],
    daily_basic_rows: list[TushareDailyBasicRow],
    adj_factor_rows: list[TushareAdjFactorRow],
) -> TradeDateSyncStats:
    stats = TradeDateSyncStats(
        trade_date=trade_date,
        daily_rows=len(daily_rows),
        daily_basic_rows=len(daily_basic_rows),
        adj_factor_rows=len(adj_factor_rows),
    )
    daily_by_code = {row.ts_code: row for row in daily_rows}
    basic_by_code = {row.ts_code: row for row in daily_basic_rows}
    stock_by_code = _active_stock_map(session, trade_date)

    kline_rows = [
        _to_kline_row(row, basic_by_code.get(row.ts_code), stock_by_code.get(row.ts_code))
        for row in daily_rows
    ]
    missing_active_codes = sorted(set(stock_by_code) - set(daily_by_code))
    for ts_code in missing_active_codes:
        stock = stock_by_code[ts_code]
        kline_rows.append(
            KLineRow(
                ts_code=ts_code,
                trade_date=trade_date,
                trade_status=0,
                is_st_row=stock.is_st,
            )
        )
    stats.suspended_rows = len(missing_active_codes)
    stats.kline_rows_written = KLineRepo(session).upsert_many(kline_rows)
    stats.affected_ts_codes.update(row.ts_code for row in kline_rows)

    adj_rows = [
        AdjFactorUpsertRow(row.ts_code, row.trade_date, row.adj_factor)
        for row in adj_factor_rows
    ]
    stats.adj_factor_rows_written = AdjFactorRepo(session).upsert_many(adj_rows)
    stats.affected_ts_codes.update(row.ts_code for row in adj_factor_rows)

    market_cap_rows = [
        _to_market_cap_row(row, daily_by_code.get(row.ts_code))
        for row in daily_basic_rows
    ]
    stats.market_cap_rows_written = MarketCapRepo(session).upsert_many(market_cap_rows)
    return stats


def _active_stock_map(session: Session, day: date) -> dict[str, StockBasic]:
    stmt = (
        select(StockBasic)
        .where(
            StockBasic.is_common.is_(True),
            StockBasic.list_date.is_not(None),
            StockBasic.list_date <= day,
            or_(StockBasic.delist_date.is_(None), StockBasic.delist_date > day),
        )
        .order_by(StockBasic.ts_code)
    )
    return {row.ts_code: row for row in session.execute(stmt).scalars().all()}


def _to_stock_repo_row(row: TushareStockBasicRow, updated_by: str) -> StockBasicRow:
    name_upper = row.name.upper()
    is_bj = row.exchange == "BSE" or row.ts_code.endswith(".BJ")
    return StockBasicRow(
        ts_code=row.ts_code,
        bs_code=_bs_code_from_ts(row.ts_code),
        name=row.name,
        market=row.exchange or row.market or _market_from_ts(row.ts_code),
        list_date=row.list_date,
        delist_date=row.delist_date,
        is_bj=is_bj,
        is_common=True,
        is_st="ST" in name_upper,
        updated_by=updated_by,
    )


def _to_kline_row(
    row: TushareDailyRow,
    daily_basic: TushareDailyBasicRow | None,
    stock: StockBasic | None,
) -> KLineRow:
    return KLineRow(
        ts_code=row.ts_code,
        trade_date=row.trade_date,
        trade_status=1,
        is_st_row=bool(stock.is_st) if stock is not None else False,
        open_raw=row.open,
        high_raw=row.high,
        low_raw=row.low,
        close_raw=row.close,
        preclose_raw=row.pre_close,
        volume=None if row.vol is None else row.vol * HUNDRED,
        amount=None if row.amount is None else row.amount * THOUSAND,
        turn=None if daily_basic is None else daily_basic.turnover_rate,
        pct_chg=row.pct_chg,
    )


def _to_market_cap_row(row: TushareDailyBasicRow, daily: TushareDailyRow | None) -> MarketCapUpsertRow:
    return MarketCapUpsertRow(
        ts_code=row.ts_code,
        market_cap_source=SOURCE_TUSHARE_DAILY_BASIC if row.total_mv is not None else SOURCE_TUSHARE_MISSING,
        total_market_cap=None if row.total_mv is None else row.total_mv * TEN_THOUSAND,
        circ_market_cap=None if row.circ_mv is None else row.circ_mv * TEN_THOUSAND,
        total_share=None if row.total_share is None else row.total_share * TEN_THOUSAND,
        liqa_share=None if row.float_share is None else row.float_share * TEN_THOUSAND,
        snapshot_close=None if daily is None else daily.close,
        snapshot_date=row.trade_date,
    )


def _bs_code_from_ts(ts_code: str) -> str:
    symbol, market = ts_code.split(".", 1)
    return f"{market.lower()}.{symbol}"


def _market_from_ts(ts_code: str) -> str:
    return ts_code.split(".", 1)[1] if "." in ts_code else ""


def _mark_running(task_repo: TaskLogRepo, task_type: str, task_key: str, triggered_by: str) -> None:
    task_repo.upsert_by_key(TaskLogRow(task_type=task_type, task_key=task_key, status=STATUS_RUNNING, created_by=triggered_by))


def _mark_failed(
    task_repo: TaskLogRepo,
    task_type: str,
    task_key: str,
    triggered_by: str,
    exc: BaseException,
) -> PipelineResult:
    _mark_finished(
        task_repo,
        task_type,
        task_key,
        triggered_by,
        STATUS_FAILED,
        error_count=1,
        error_summary={"message": str(exc)},
    )
    return PipelineResult(task_type, task_key, STATUS_FAILED, error_count=1, error_summary={"message": str(exc)})


def _mark_finished(
    task_repo: TaskLogRepo,
    task_type: str,
    task_key: str,
    triggered_by: str,
    status: str,
    *,
    expected_count: int | None = None,
    success_count: int | None = None,
    missing_count: int | None = None,
    error_count: int | None = None,
    error_summary: dict[str, object] | None = None,
) -> None:
    task_repo.upsert_by_key(
        TaskLogRow(
            task_type=task_type,
            task_key=task_key,
            status=status,
            created_by=triggered_by,
            finished_at=datetime.now(UTC),
            expected_count=expected_count,
            success_count=success_count,
            missing_count=missing_count,
            error_count=error_count,
            error_summary=error_summary,
        )
    )


def _write_child_status(
    session_factory: Callable[[], AbstractContextManager[Session]],
    task_key: str,
    triggered_by: str,
    status: str,
    *,
    task_type: str = TASK_TUSHARE_UPDATE_DAILY,
) -> None:
    with session_factory() as session:
        TaskLogRepo(session).upsert_by_key(
            TaskLogRow(
                task_type=task_type,
                task_key=task_key,
                status=status,
                created_by=triggered_by,
            )
        )


def _write_child_failure(
    session_factory: Callable[[], AbstractContextManager[Session]],
    task_key: str,
    triggered_by: str,
    message: str,
    *,
    task_type: str = TASK_TUSHARE_UPDATE_DAILY,
) -> None:
    with session_factory() as session:
        _mark_finished(
            TaskLogRepo(session),
            task_type,
            task_key,
            triggered_by,
            STATUS_FAILED,
            error_count=1,
            error_summary={"message": message},
        )


def _write_parent_progress(
    session_factory: Callable[[], AbstractContextManager[Session]],
    task_key: str,
    triggered_by: str,
    expected: int,
    succeeded: int,
    failed: int,
    rows_written: int,
    *,
    current_date: date | None,
    failed_dates: list[str],
    cache_status: str,
) -> None:
    with session_factory() as session:
        TaskLogRepo(session).upsert_by_key(
            TaskLogRow(
                task_type=TASK_TUSHARE_INIT,
                task_key=task_key,
                status=STATUS_RUNNING,
                created_by=triggered_by,
                expected_count=expected,
                success_count=succeeded,
                missing_count=max(expected - succeeded - failed, 0),
                error_count=failed,
                error_summary={
                    "current_date": current_date.isoformat() if current_date else None,
                    "rows_written": rows_written,
                    "failed_dates": failed_dates[:20],
                    "cache_status": cache_status,
                },
            )
        )


def _finish_parent(
    session_factory: Callable[[], AbstractContextManager[Session]],
    task_key: str,
    triggered_by: str,
    status: str,
    expected: int,
    succeeded: int,
    failed: int,
    rows_written: int,
    failed_dates: list[str],
    cache_status: str,
) -> None:
    with session_factory() as session:
        _mark_finished(
            TaskLogRepo(session),
            TASK_TUSHARE_INIT,
            task_key,
            triggered_by,
            status,
            expected_count=expected,
            success_count=succeeded,
            missing_count=max(expected - succeeded - failed, 0),
            error_count=failed,
            error_summary={
                "rows_written": rows_written,
                "failed_dates": failed_dates[:20],
                "cache_status": cache_status,
            },
        )


def _ensure_success(result: PipelineResult) -> None:
    if result.status != STATUS_SUCCESS:
        message = None
        if result.error_summary is not None:
            message = result.error_summary.get("message")
        raise RuntimeError(f"{result.task_type} failed: {message or result.status}")
