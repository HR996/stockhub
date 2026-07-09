"""Stock detail aggregation service."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.repositories.adj_factor_repo import AdjFactorRepo
from app.repositories.kline_repo import KLineRepo
from app.repositories.market_cap_repo import MarketCapRepo
from app.repositories.qfq_cache_repo import QfqCacheRepo
from app.repositories.stock_repo import StockBasicRepo
from app.repositories.sw_repo import SWMemberRepo


def get_stock_detail(session: Session, ts_code: str) -> dict[str, Any] | None:
    stock = StockBasicRepo(session).get_by_ts_code(ts_code)
    if stock is None:
        return None
    cap = MarketCapRepo(session).get_by_ts_code(ts_code)
    sw = SWMemberRepo(session).get_by_ts_code(ts_code)
    latest_date = KLineRepo(session).latest_trade_date()
    latest = KLineRepo(session).get(ts_code, latest_date) if latest_date else None
    latest_qfq = QfqCacheRepo(session).latest_for_stock(ts_code)
    return {
        "basic": {
            "ts_code": stock.ts_code,
            "bs_code": stock.bs_code,
            "name": stock.name,
            "market": stock.market,
            "list_date": stock.list_date.isoformat() if stock.list_date else None,
            "delist_date": stock.delist_date.isoformat() if stock.delist_date else None,
            "is_bj": stock.is_bj,
            "is_common": stock.is_common,
            "is_st": stock.is_st,
            "updated_at": stock.updated_at.isoformat() if stock.updated_at else None,
        },
        "latest_trade": {
            "trade_date": latest.trade_date.isoformat() if latest else None,
            "trade_status": latest.trade_status if latest else None,
            "close_raw": _json(latest.close_raw) if latest else None,
            "close_qfq": _json(latest_qfq.close) if latest_qfq else None,
        },
        "market_cap": None if cap is None else {
            "total_market_cap": _json(cap.total_market_cap),
            "circ_market_cap": _json(cap.circ_market_cap),
            "snapshot_date": cap.snapshot_date.isoformat() if cap.snapshot_date else None,
            "market_cap_source": cap.market_cap_source,
        },
        "industry": {
            "csrc": None,
            "sw": None if sw is None else {
                "l1_index_code": sw.l1_index_code,
                "l1_name": sw.l1_name,
                "l2_index_code": sw.l2_index_code,
                "l2_name": sw.l2_name,
                "l3_index_code": sw.l3_index_code,
                "l3_name": sw.l3_name,
                "in_date": sw.in_date.isoformat() if sw.in_date else None,
            },
        },
    }


def get_stock_kline(
    session: Session,
    ts_code: str,
    *,
    start: date | None,
    end: date | None,
    adjust: str,
) -> dict[str, Any]:
    if adjust != "qfq":
        raise ValidationError("VALIDATION_INVALID_ADJUST", "adjust must be qfq")
    end = end or date.today()
    start = start or (end - timedelta(days=240))
    if (end - start).days > 366 * 3:
        raise ValidationError("VALIDATION_DATE_RANGE_TOO_LARGE", "kline range max is 3 years")
    latest_factor = AdjFactorRepo(session).latest_for_stock(ts_code)
    latest_cache = QfqCacheRepo(session).latest_for_stock(ts_code)
    if latest_factor is None:
        raise ValidationError(
            "QFQ_CACHE_STALE", f"no adjustment factor available for {ts_code}"
        )
    if (
        latest_cache is None
        or latest_cache.base_adj_factor != latest_factor.adj_factor
    ):
        raise ValidationError(
            "QFQ_CACHE_STALE", f"QFQ cache is stale for {ts_code}"
        )
    rows = QfqCacheRepo(session).list_by_stock(ts_code, start, end)
    raw_by_date = {
        row.trade_date: row
        for row in KLineRepo(session).list_by_stock(ts_code, start, end)
    }
    return {
        "ts_code": ts_code,
        "adjust": "qfq",
        "base_date": latest_factor.trade_date.isoformat(),
        "items": [
            {
                "trade_date": r.trade_date.isoformat(),
                "open": _json(r.open),
                "high": _json(r.high),
                "low": _json(r.low),
                "close": _json(r.close),
                "volume": _json(raw_by_date[r.trade_date].volume)
                if r.trade_date in raw_by_date else None,
                "amount": _json(raw_by_date[r.trade_date].amount)
                if r.trade_date in raw_by_date else None,
                "trade_status": raw_by_date[r.trade_date].trade_status
                if r.trade_date in raw_by_date else 1,
            }
            for r in rows
        ],
    }


def _json(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
