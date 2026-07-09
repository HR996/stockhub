"""CLI runner for the Tushare-backed data service."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime

from app.adapters.tushare_adapter import tushare_session
from app.core.db import session_scope
from app.data_service.tushare_pipeline import (
    STATUS_RUNNING,
    TASK_TUSHARE_QFQ_CACHE,
    TASK_TUSHARE_UPDATE_DAILY,
    init_range_from_tushare,
    sync_stock_basic_from_tushare,
    sync_trade_calendar_from_tushare,
    update_one_day_from_tushare,
)
from app.models.k_line_daily import KLineDaily
from app.repositories.qfq_cache_repo import (
    rebuild_qfq_cache,
    refresh_qfq_cache_for_day,
)
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args()
    triggered_by = args.triggered_by

    if args.command == "rebuild-qfq-cache":
        with session_scope() as session:
            stocks, rows = rebuild_qfq_cache(session, args.ts_code or None)
            TaskLogRepo(session).upsert_by_key(
                TaskLogRow(
                    task_type=TASK_TUSHARE_QFQ_CACHE,
                    task_key=(
                        f"{TASK_TUSHARE_QFQ_CACHE}:"
                        + (",".join(sorted(args.ts_code)) if args.ts_code else "ALL")
                    ),
                    status="SUCCESS",
                    created_by=triggered_by,
                    finished_at=datetime.now(UTC),
                    expected_count=stocks,
                    success_count=stocks,
                    error_summary={"rows_written": rows},
                )
            )
        logger.info("rebuild-qfq-cache done: stocks=%s rows=%s", stocks, rows)
        return

    with tushare_session() as pro:
        if args.command == "init":
            result = init_range_from_tushare(
                pro,
                session_scope,
                start=_parse_date(args.start),
                end=_parse_date(args.end),
                triggered_by=triggered_by,
                force=args.force,
            )
        elif args.command == "update":
            trade_date = _parse_date(args.date)
            task_key = f"{TASK_TUSHARE_UPDATE_DAILY}:{trade_date.isoformat()}"
            with session_scope() as session:
                TaskLogRepo(session).upsert_by_key(
                    TaskLogRow(
                        task_type=TASK_TUSHARE_UPDATE_DAILY,
                        task_key=task_key,
                        status=STATUS_RUNNING,
                        created_by=triggered_by,
                    )
                )
            with session_scope() as session:
                result = update_one_day_from_tushare(
                    pro,
                    session,
                    trade_date=trade_date,
                    triggered_by=triggered_by,
                )
            cache_key = f"{TASK_TUSHARE_QFQ_CACHE}:{trade_date.isoformat()}"
            with session_scope() as session:
                TaskLogRepo(session).upsert_by_key(
                    TaskLogRow(
                        task_type=TASK_TUSHARE_QFQ_CACHE,
                        task_key=cache_key,
                        status=STATUS_RUNNING,
                        created_by=triggered_by,
                    )
                )
            try:
                with session_scope() as session:
                    codes = {
                        row.ts_code
                        for row in session.query(KLineDaily).filter_by(
                            trade_date=trade_date
                        )
                    }
                    rebuilt, rows = refresh_qfq_cache_for_day(
                        session, trade_date, codes
                    )
                    TaskLogRepo(session).upsert_by_key(
                        TaskLogRow(
                            task_type=TASK_TUSHARE_QFQ_CACHE,
                            task_key=cache_key,
                            status="SUCCESS",
                            created_by=triggered_by,
                            finished_at=datetime.now(UTC),
                            expected_count=len(codes),
                            success_count=len(codes),
                            error_summary={"rebuilt_stocks": rebuilt, "rows_written": rows},
                        )
                    )
            except Exception as exc:
                with session_scope() as session:
                    TaskLogRepo(session).upsert_by_key(
                        TaskLogRow(
                            task_type=TASK_TUSHARE_QFQ_CACHE,
                            task_key=cache_key,
                            status="FAILED",
                            created_by=triggered_by,
                            finished_at=datetime.now(UTC),
                            error_count=1,
                            error_summary={"message": str(exc)},
                        )
                    )
                raise
        elif args.command == "sync-basic":
            with session_scope() as session:
                result = sync_stock_basic_from_tushare(
                    pro, session, triggered_by=triggered_by
                )
        elif args.command == "sync-calendar":
            with session_scope() as session:
                result = sync_trade_calendar_from_tushare(
                    pro,
                    session,
                    start=_parse_date(args.start),
                    end=_parse_date(args.end),
                    triggered_by=triggered_by,
                )
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
    if result.status not in ("SUCCESS",):
        raise SystemExit(1)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tushare data initialization/update service")
    parser.add_argument("--triggered-by", default="data_service", help="User label stored in data_update_task.created_by")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize stock/calendar/daily data for a date range")
    init.add_argument("--start", required=True, help="YYYY-MM-DD")
    init.add_argument("--end", required=True, help="YYYY-MM-DD")
    init.add_argument(
        "--force", action="store_true", help="Re-fetch dates already committed successfully"
    )

    update = sub.add_parser("update", help="Update one trading date")
    update.add_argument("--date", required=True, help="YYYY-MM-DD")

    calendar = sub.add_parser("sync-calendar", help="Sync trade calendar for a date range")
    calendar.add_argument("--start", required=True, help="YYYY-MM-DD")
    calendar.add_argument("--end", required=True, help="YYYY-MM-DD")

    sub.add_parser("sync-basic", help="Sync stock_basic")

    rebuild = sub.add_parser(
        "rebuild-qfq-cache", help="Rebuild latest-basedate QFQ display cache"
    )
    rebuild.add_argument(
        "--ts-code", action="append", default=[], help="Stock code; repeat as needed"
    )
    return parser


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


if __name__ == "__main__":
    main()
