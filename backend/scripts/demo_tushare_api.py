#!/usr/bin/env python
"""Smoke test Tushare APIs used by the data service without touching the DB.

Usage:
    cd backend
    set -a; source .env; set +a
    ./.venv/bin/python scripts/demo_tushare_api.py --date 2026-07-08

This script only reads Tushare and prints row counts/sample rows. It does not
write database tables or data_update_task.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.adapters.tushare_adapter import (
    fetch_adj_factor_by_trade_date,
    fetch_daily_basic_by_trade_date,
    fetch_daily_by_trade_date,
    fetch_stock_basic,
    fetch_trade_cal,
    tushare_session,
)


def main() -> None:
    args = _parse_args()
    day = date.fromisoformat(args.date)
    start = date.fromisoformat(args.calendar_start) if args.calendar_start else day - timedelta(days=7)
    end = date.fromisoformat(args.calendar_end) if args.calendar_end else day + timedelta(days=7)

    with tushare_session() as pro:
        _run_step("stock_basic", lambda: fetch_stock_basic(pro), args.samples)
        _run_step("trade_cal", lambda: fetch_trade_cal(pro, start, end), args.samples)
        _run_step("daily", lambda: fetch_daily_by_trade_date(pro, day), args.samples)
        _run_step("daily_basic", lambda: fetch_daily_basic_by_trade_date(pro, day), args.samples)
        _run_step("adj_factor", lambda: fetch_adj_factor_by_trade_date(pro, day), args.samples)


def _run_step(name: str, fn, samples: int) -> None:
    print(f"\n== {name} ==")
    try:
        rows = fn()
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return
    print(f"rows: {len(rows)}")
    for row in rows[:samples]:
        print(row)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demo Tushare APIs used by istock data service")
    parser.add_argument("--date", required=True, help="Trading date to query, YYYY-MM-DD")
    parser.add_argument("--calendar-start", help="Calendar range start, YYYY-MM-DD; default date-7d")
    parser.add_argument("--calendar-end", help="Calendar range end, YYYY-MM-DD; default date+7d")
    parser.add_argument("--samples", type=int, default=3, help="Sample rows to print for each API")
    return parser.parse_args()


if __name__ == "__main__":
    main()
