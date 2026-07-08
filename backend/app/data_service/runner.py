"""CLI runner for the Tushare-backed data service."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from app.adapters.tushare_adapter import tushare_session
from app.core.db import session_scope
from app.data_service.tushare_pipeline import (
    init_range_from_tushare,
    recompute_adjusted_prices,
    sync_stock_basic_from_tushare,
    sync_trade_calendar_from_tushare,
    update_one_day_from_tushare,
)
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args()
    triggered_by = args.triggered_by

    with tushare_session() as pro, session_scope() as session:
        if args.command == "init":
            result = init_range_from_tushare(
                pro,
                session,
                start=_parse_date(args.start),
                end=_parse_date(args.end),
                triggered_by=triggered_by,
            )
        elif args.command == "update":
            result = update_one_day_from_tushare(
                pro,
                session,
                trade_date=_parse_date(args.date),
                triggered_by=triggered_by,
            )
        elif args.command == "sync-basic":
            result = sync_stock_basic_from_tushare(pro, session, triggered_by=triggered_by)
        elif args.command == "sync-calendar":
            result = sync_trade_calendar_from_tushare(
                pro,
                session,
                start=_parse_date(args.start),
                end=_parse_date(args.end),
                triggered_by=triggered_by,
            )
        elif args.command == "recompute-adjusted":
            start = _parse_date(args.start)
            end = _parse_date(args.end)
            rows = recompute_adjusted_prices(session, start=start, end=end)
            TaskLogRepo(session).upsert_by_key(
                TaskLogRow(
                    task_type="TUSHARE_RECOMPUTE_ADJUSTED",
                    task_key=f"TUSHARE_RECOMPUTE_ADJUSTED:{start.isoformat()}:{end.isoformat()}",
                    status="SUCCESS",
                    created_by=triggered_by,
                    success_count=rows,
                    error_summary={"adjusted_rows": rows},
                )
            )
            logger.info("recompute-adjusted done: %s rows", rows)
            return
        else:
            raise SystemExit(f"unknown command: {args.command}")

    logger.info(
        "%s done: status=%s expected=%s success=%s missing=%s errors=%s rows=%s",
        result.task_type,
        result.status,
        result.expected_count,
        result.success_count,
        result.missing_count,
        result.error_count,
        result.rows_written,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tushare data initialization/update service")
    parser.add_argument("--triggered-by", default="data_service", help="User label stored in data_update_task.created_by")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize stock/calendar/daily data for a date range")
    init.add_argument("--start", required=True, help="YYYY-MM-DD")
    init.add_argument("--end", required=True, help="YYYY-MM-DD")

    update = sub.add_parser("update", help="Update one trading date")
    update.add_argument("--date", required=True, help="YYYY-MM-DD")

    calendar = sub.add_parser("sync-calendar", help="Sync trade calendar for a date range")
    calendar.add_argument("--start", required=True, help="YYYY-MM-DD")
    calendar.add_argument("--end", required=True, help="YYYY-MM-DD")

    sub.add_parser("sync-basic", help="Sync stock_basic")

    recompute = sub.add_parser("recompute-adjusted", help="Recompute qfq/hfq columns from local raw prices and adj factors")
    recompute.add_argument("--start", required=True, help="YYYY-MM-DD")
    recompute.add_argument("--end", required=True, help="YYYY-MM-DD")
    return parser


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    main()
