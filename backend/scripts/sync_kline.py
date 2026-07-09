"""K-line sync script — supports incremental batch runs and partial adjust-flag fetches.

Usage examples:

  # Test with 5 stocks, raw only (cheapest — ~5 baostock calls)
  python scripts/sync_kline.py --adjust raw --limit 5

  # Full market, qfq only (one pass ~5000 calls)
  python scripts/sync_kline.py --adjust qfq

  # Resume after interruption: skip stocks already in DB for this adjust flag
  python scripts/sync_kline.py --adjust qfq --resume

  # Full market, hfq only
  python scripts/sync_kline.py --adjust hfq

  # Full market, all three flags (default — ~15000 calls, use on quiet days)
  python scripts/sync_kline.py

  # Specific date range
  python scripts/sync_kline.py --adjust raw --start 2024-01-01 --end 2024-12-31

  # Only active stocks (listed, not delisted) — default
  # Pass --all to include delisted stocks
  python scripts/sync_kline.py --adjust raw --limit 10 --all

Run from backend/ directory:
  DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock' \\
      python scripts/sync_kline.py [options]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync k_line_daily from baostock")
    parser.add_argument(
        "--adjust",
        choices=["raw", "qfq", "hfq", "all"],
        default="all",
        help="Which adjust flag(s) to fetch. Default: all three.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only process the first N stocks (for testing).",
    )
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="Start date (default: 3 years ago).",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="End date (default: today).",
    )
    parser.add_argument(
        "--all",
        dest="include_delisted",
        action="store_true",
        default=False,
        help="Include delisted stocks (default: active only).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Skip stocks that already have data in k_line_daily for the given adjust flag.",
    )
    parser.add_argument(
        "--codes-file",
        dest="codes_file",
        default=None,
        metavar="FILE",
        help="Text file with one ts_code per line. Only these stocks are processed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from datetime import UTC, datetime

    from sqlalchemy import func, select

    from app.adapters.baostock_adapter import baostock_session
    from app.core.db import session_scope
    from app.models.k_line_daily import KLineDaily
    from app.repositories.kline_repo import KLineRepo
    from app.repositories.stock_repo import StockBasicRepo
    from app.repositories.task_log_repo import TaskLogRepo
    from app.services.sync_kline_service import AdjustMode, sync_kline_for_stocks

    today = datetime.now(UTC).date()
    start_date: date = args.start or date(today.year - 3, 1, 1)
    end_date: date = args.end or today

    if args.adjust not in ("all", "raw"):
        raise SystemExit("legacy Baostock sync now supports raw data only")
    adjust_flags: list[AdjustMode] = ["raw"]

    # Resolve stock list
    with session_scope() as db:
        if args.codes_file:
            with open(args.codes_file) as f:
                ts_codes = [line.strip() for line in f if line.strip()]
            logger.info("--codes-file: loaded %d stocks from %s", len(ts_codes), args.codes_file)
        elif args.include_delisted:
            ts_codes = [r.ts_code for r in StockBasicRepo(db).list_all()]
        else:
            ts_codes = StockBasicRepo(db).list_active_ts_codes_at(today)

        if args.resume:
            col = KLineDaily.close_raw
            done_codes = {
                row[0] for row in db.execute(
                    select(func.distinct(KLineDaily.ts_code)).where(col.isnot(None))
                ).all()
            }
            before = len(ts_codes)
            ts_codes = [c for c in ts_codes if c not in done_codes]
            logger.info("--resume: skipping %d already-done stocks, %d remaining", before - len(ts_codes), len(ts_codes))

    if not ts_codes:
        logger.info("No stocks to process (all done or stock_basic is empty).")
        sys.exit(0)

    if args.limit:
        ts_codes = ts_codes[: args.limit]

    logger.info(
        "sync_kline: %d stocks | %s → %s | flags=%s",
        len(ts_codes),
        start_date,
        end_date,
        adjust_flags,
    )

    with baostock_session(), session_scope() as db:
        result = sync_kline_for_stocks(
            ts_codes=ts_codes,
            start_date=start_date,
            end_date=end_date,
            kline_repo=KLineRepo(db),
            task_repo=TaskLogRepo(db),
            triggered_by="sync_kline_script",
            adjust_flags=adjust_flags,
            session=db,
        )

    logger.info("status:        %s", result.status)
    logger.info("stocks OK:     %d / %d", result.success_count, result.expected_count)
    logger.info("rows written:  %d", result.rows_written)
    if result.missing_count:
        logger.warning("missing:       %d  (no rows returned)", result.missing_count)
    if result.error_count:
        logger.warning("errors:        %d  — see error_summary below", result.error_count)
        logger.warning("  %s", result.error_summary)

    if result.status == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    main()
