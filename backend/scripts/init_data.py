"""One-shot init script — run once at deployment to populate stock_basic + trade_calendar.

Usage:
    cd backend
    DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock' \\
        python scripts/init_data.py
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    from app.adapters.baostock_adapter import baostock_session
    from app.core.db import session_scope
    from app.repositories.stock_repo import StockBasicRepo
    from app.repositories.task_log_repo import TaskLogRepo
    from app.repositories.trade_cal_repo import TradeCalRepo
    from app.services.sync_basic_service import sync_stock_basic, sync_trade_calendar

    with baostock_session():
        # --- stock_basic ---
        logger.info("Step 1/2: sync_stock_basic ...")
        with session_scope() as db:
            result = sync_stock_basic(
                stock_repo=StockBasicRepo(db),
                task_repo=TaskLogRepo(db),
                triggered_by="init_script",
            )
        if result.status == "SUCCESS":
            logger.info("  stock_basic OK — %d rows", result.success_count)
        else:
            logger.error("  stock_basic FAILED: %s", result.error_message)
            sys.exit(1)

        # --- trade_calendar ---
        logger.info("Step 2/2: sync_trade_calendar ...")
        with session_scope() as db:
            result = sync_trade_calendar(
                trade_cal_repo=TradeCalRepo(db),
                task_repo=TaskLogRepo(db),
                triggered_by="init_script",
            )
        if result.status == "SUCCESS":
            logger.info(
                "  trade_calendar OK — %d/%d rows (range default: last 3y + next year)",
                result.success_count,
                result.expected_count,
            )
        else:
            logger.error("  trade_calendar FAILED: %s", result.error_message)
            sys.exit(1)

    logger.info("init_data complete.")


if __name__ == "__main__":
    main()
