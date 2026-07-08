#!/usr/bin/env python
"""Standalone raw Tushare API demo.

This script intentionally does not import app.adapters or app.data_service. It
only calls the official tushare package so you can isolate token/IP/permission
issues from istock's adapter layer.

Usage:
    cd backend
    set -a; source .env; set +a
    ./.venv/bin/python scripts/demo_tushare_raw_api.py --date 2026-07-08
"""

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from typing import Any


def main() -> None:
    args = _parse_args()
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise SystemExit("TUSHARE_TOKEN is not set")

    import tushare as ts

    day = date.fromisoformat(args.date)
    cal_start = date.fromisoformat(args.calendar_start) if args.calendar_start else day - timedelta(days=7)
    cal_end = date.fromisoformat(args.calendar_end) if args.calendar_end else day + timedelta(days=7)
    trade_date = day.strftime("%Y%m%d")

    ts.set_token(token)
    pro = ts.pro_api()

    if args.start or args.end:
        range_start = date.fromisoformat(args.start or args.date)
        range_end = date.fromisoformat(args.end or args.date)
        _run_range(pro, range_start, range_end, args.samples)
        return

    _run(
        "stock_basic",
        lambda: pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,exchange,list_status,list_date,delist_date",
        ),
        args.samples,
    )
    _run(
        "trade_cal",
        lambda: pro.trade_cal(
            exchange="SSE",
            start_date=cal_start.strftime("%Y%m%d"),
            end_date=cal_end.strftime("%Y%m%d"),
        ),
        args.samples,
    )
    _run("daily", lambda: pro.daily(trade_date=trade_date, offset=0, limit=6000), args.samples)
    _run(
        "daily_basic",
        lambda: pro.daily_basic(
            trade_date=trade_date,
            fields=(
                "ts_code,trade_date,turnover_rate,turnover_rate_f,total_share,"
                "float_share,free_share,total_mv,circ_mv"
            ),
            offset=0,
            limit=6000,
        ),
        args.samples,
    )
    _run("adj_factor", lambda: pro.adj_factor(trade_date=trade_date, offset=0, limit=6000), args.samples)


def _run_range(pro: Any, start: date, end: date, samples: int) -> None:
    print(f"range: {start.isoformat()} -> {end.isoformat()}")
    cal = pro.trade_cal(
        exchange="SSE",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    open_days = [
        date.fromisoformat(f"{str(row.cal_date)[:4]}-{str(row.cal_date)[4:6]}-{str(row.cal_date)[6:8]}")
        for row in cal.itertuples()
        if str(row.is_open) == "1"
    ]
    print(f"open days: {len(open_days)}")
    if samples:
        print("sample days:", ", ".join(day.isoformat() for day in open_days[:samples]))

    for i, day in enumerate(open_days, 1):
        trade_date = day.strftime("%Y%m%d")
        print(f"\n[{i}/{len(open_days)}] {day.isoformat()}")
        ok = True
        ok = _run_count("daily", lambda trade_date=trade_date: pro.daily(trade_date=trade_date, offset=0, limit=6000)) and ok
        ok = _run_count(
            "daily_basic",
            lambda trade_date=trade_date: pro.daily_basic(
                trade_date=trade_date,
                fields=(
                    "ts_code,trade_date,turnover_rate,turnover_rate_f,total_share,"
                    "float_share,free_share,total_mv,circ_mv"
                ),
                offset=0,
                limit=6000,
            ),
        ) and ok
        ok = _run_count("adj_factor", lambda trade_date=trade_date: pro.adj_factor(trade_date=trade_date, offset=0, limit=6000)) and ok
        if not ok:
            print("stopping at first failed trading day")
            return


def _run(name: str, fn: Any, samples: int) -> None:
    print(f"\n== {name} ==")
    try:
        df = fn()
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return

    print(f"rows: {len(df)}")
    if len(df) == 0:
        return
    print(df.head(samples).to_string(index=False))


def _run_count(name: str, fn: Any) -> bool:
    try:
        df = fn()
    except Exception as exc:
        print(f"{name}: FAILED: {type(exc).__name__}: {exc}")
        return False
    print(f"{name}: rows={len(df)}")
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone raw Tushare API smoke test")
    parser.add_argument("--date", required=True, help="Trading date to query, YYYY-MM-DD")
    parser.add_argument("--calendar-start", help="Calendar range start, YYYY-MM-DD; default date-7d")
    parser.add_argument("--calendar-end", help="Calendar range end, YYYY-MM-DD; default date+7d")
    parser.add_argument("--start", help="Run full daily/daily_basic/adj_factor loop from this date")
    parser.add_argument("--end", help="Run full daily/daily_basic/adj_factor loop to this date")
    parser.add_argument("--samples", type=int, default=3, help="Sample rows to print for each API")
    return parser.parse_args()


if __name__ == "__main__":
    main()
