"""Daily sync orchestrator + APScheduler wiring.

Runs one composite daily job under a single Tushare session:
  1. sync_stock_basic
  2. sync_trade_calendar
  3. daily raw data update followed by an independent QFQ cache refresh

Design constraints:
- Single `tushare_session()` context wraps the steps
- Each step handles its own errors and writes its own `data_update_task` row
- On `AdapterQuotaExceededError`, remaining steps are skipped (do not burn quota)
- APScheduler is opt-in via `SCHEDULER_ENABLED=true`; default OFF so tests / local
  dev never hit Tushare automatically
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.adapters.tushare_adapter import tushare_session
from app.core.config import settings
from app.core.db import session_scope
from app.core.errors import AdapterAuthError, AdapterError, AdapterQuotaExceededError
from app.data_service.tushare_pipeline import (
    sync_stock_basic_from_tushare,
    sync_trade_calendar_from_tushare,
    update_one_day_from_tushare,
)
from app.models.k_line_daily import KLineDaily
from app.repositories.qfq_cache_repo import refresh_qfq_cache_for_day
from app.repositories.sw_repo import SWClassifyRepo, SWMemberRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.repositories.trade_cal_repo import TradeCalRepo
from app.services.sw_sync_service import SWSyncResult, sync_sw_industry

logger = logging.getLogger(__name__)


@dataclass
class DailySyncReport:
    today: date
    steps: dict[str, str] = field(default_factory=dict)  # step_name -> "SUCCESS" / "FAILED" / "SKIPPED"
    quota_exhausted: bool = False
    errors: dict[str, str] = field(default_factory=dict)


def _record(report: DailySyncReport, step: str, status: str, error: Exception | None = None) -> None:
    report.steps[step] = status
    if error is not None:
        report.errors[step] = f"{type(error).__name__}: {error}"


def run_daily_sync(
    today: date | None = None,
    session_factory: Callable[[], session_scope] = session_scope,
) -> DailySyncReport:
    """Run stock_basic → trade_cal → daily data update under one Tushare session.

    Args:
      today: injectable "today"; defaults to current UTC date.
      session_factory: callable returning a DB session context (test seam).
    """
    today = today or datetime.now(UTC).date()
    report = DailySyncReport(today=today)
    triggered_by = settings.scheduler_triggered_by

    try:
        with tushare_session() as pro:
            _step_stock_basic(report, session_factory, pro, triggered_by, today)
            if report.quota_exhausted:
                return report
            _step_trade_cal(report, session_factory, pro, triggered_by, today)
            if report.quota_exhausted:
                return report
            _step_daily_data(report, session_factory, pro, triggered_by, today)
            if report.quota_exhausted:
                return report
    except AdapterQuotaExceededError as exc:
        logger.error("tushare quota exhausted at session setup: %s", exc)
        report.quota_exhausted = True
    except Exception as exc:
        logger.exception("run_daily_sync unexpected error: %s", exc)
        _record(report, "session", "FAILED", exc)

    return report


def _step_stock_basic(
    report: DailySyncReport,
    session_factory: Callable,
    pro: object,
    triggered_by: str,
    today: date,
) -> None:
    try:
        with session_factory() as db:
            r = sync_stock_basic_from_tushare(
                pro,
                db,
                triggered_by=triggered_by,
                today=today,
            )
        _record(report, "stock_basic", r.status)
    except AdapterQuotaExceededError as exc:
        _record(report, "stock_basic", "FAILED", exc)
        report.quota_exhausted = True
    except Exception as exc:
        logger.exception("stock_basic step failed: %s", exc)
        _record(report, "stock_basic", "FAILED", exc)


def _step_trade_cal(
    report: DailySyncReport,
    session_factory: Callable,
    pro: object,
    triggered_by: str,
    today: date,
) -> None:
    try:
        with session_factory() as db:
            r = sync_trade_calendar_from_tushare(
                pro,
                db,
                triggered_by=triggered_by,
                start=date(today.year - 3, 1, 1),
                end=date(today.year + 1, 12, 31),
                today=today,
            )
        _record(report, "trade_cal", r.status)
    except AdapterQuotaExceededError as exc:
        _record(report, "trade_cal", "FAILED", exc)
        report.quota_exhausted = True
    except Exception as exc:
        logger.exception("trade_cal step failed: %s", exc)
        _record(report, "trade_cal", "FAILED", exc)


def _step_daily_data(
    report: DailySyncReport,
    session_factory: Callable,
    pro: object,
    triggered_by: str,
    today: date,
) -> None:
    """Incremental daily sync for today's daily/daily_basic/adj_factor data."""
    try:
        with session_factory() as db:
            trade_repo = TradeCalRepo(db)
            if not trade_repo.is_trading_day(today):
                _record(report, "kline", "SKIPPED")
                _record(report, "market_cap", "SKIPPED")
                return
            r = update_one_day_from_tushare(
                pro,
                db,
                trade_date=today,
                triggered_by=triggered_by,
            )
        with session_factory() as db:
            codes = {
                row.ts_code
                for row in db.query(KLineDaily).filter_by(trade_date=today)
            }
            refresh_qfq_cache_for_day(db, today, codes)
        _record(report, "kline", r.status)
        _record(report, "market_cap", r.status)
        _record(report, "qfq_cache", "SUCCESS")
    except AdapterQuotaExceededError as exc:
        _record(report, "kline", "FAILED", exc)
        _record(report, "market_cap", "FAILED", exc)
        _record(report, "qfq_cache", "FAILED", exc)
        report.quota_exhausted = True
    except Exception as exc:
        logger.exception("daily data step failed: %s", exc)
        _record(report, "kline", "FAILED", exc)
        _record(report, "market_cap", "FAILED", exc)


def build_scheduler() -> AsyncIOScheduler | None:
    """Return an AsyncIOScheduler configured to run `run_daily_sync` daily.

    Returns None when neither the daily nor the weekly SW sync is enabled.
    Independent env switches: `SCHEDULER_ENABLED` (daily) and `SCHEDULER_SW_ENABLED` (weekly SW).
    """
    daily_on = settings.scheduler_enabled
    sw_on = settings.scheduler_sw_enabled
    if not daily_on and not sw_on:
        logger.info(
            "scheduler disabled (set SCHEDULER_ENABLED=true and/or SCHEDULER_SW_ENABLED=true)"
        )
        return None

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    if daily_on:
        daily_trigger = CronTrigger(
            hour=settings.scheduler_hour,
            minute=settings.scheduler_minute,
            timezone="Asia/Shanghai",
        )
        scheduler.add_job(
            _run_daily_sync_job,
            trigger=daily_trigger,
            id="daily_sync",
            name="istock daily sync (Tushare stock_basic → trade_cal → daily data)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    if sw_on:
        sw_trigger = CronTrigger(
            day_of_week=settings.scheduler_sw_day_of_week,
            hour=settings.scheduler_sw_hour,
            minute=settings.scheduler_sw_minute,
            timezone="Asia/Shanghai",
        )
        scheduler.add_job(
            _run_weekly_sw_sync_job,
            trigger=sw_trigger,
            id="sw_weekly_sync",
            name="istock weekly SW industry sync (Tushare)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    return scheduler


def _run_daily_sync_job() -> None:
    """Scheduler entrypoint — no args, logs the report."""
    report = run_daily_sync()
    logger.info("daily sync report: %s", report)


def run_weekly_sw_sync(
    today: date | None = None,
    session_factory: Callable[[], session_scope] = session_scope,
) -> SWSyncResult | None:
    """Fetch SW2021 classify + membership from Tushare and refresh the two SW tables.

    Idempotent per calendar day via the SYNC_SW_INDUSTRY:{today} task key.
    Returns None only when the tushare session itself cannot be established (auth error).
    """
    today = today or datetime.now(UTC).date()
    triggered_by = settings.scheduler_triggered_by
    try:
        with tushare_session() as pro, session_factory() as db:
            return sync_sw_industry(
                pro=pro,
                classify_repo=SWClassifyRepo(db),
                member_repo=SWMemberRepo(db),
                task_repo=TaskLogRepo(db),
                triggered_by=triggered_by,
                today=today,
            )
    except AdapterAuthError as exc:
        logger.error("SW sync aborted — tushare auth error: %s", exc)
        return None
    except AdapterError as exc:
        logger.exception("SW sync adapter error: %s", exc)
        return None
    except Exception as exc:
        logger.exception("SW sync unexpected error: %s", exc)
        return None


def _run_weekly_sw_sync_job() -> None:
    """APScheduler entrypoint — no args."""
    result = run_weekly_sw_sync()
    logger.info("weekly SW sync result: %s", result)


def main() -> None:
    """CLI entry: `python -m app.services.scheduler` triggers one immediate run."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    report = run_daily_sync()
    print(report)


if __name__ == "__main__":
    main()


__all__ = [
    "DailySyncReport",
    "SWSyncResult",
    "build_scheduler",
    "run_daily_sync",
    "run_weekly_sw_sync",
]
