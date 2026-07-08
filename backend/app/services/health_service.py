"""Data-health summary service (P1-07).

Aggregates per-table row count and latest update timestamp for the four core
data-base tables. No business logic beyond the aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_update_task import DataUpdateTask
from app.models.k_line_daily import KLineDaily
from app.models.latest_market_cap import LatestMarketCap
from app.models.stock_basic import StockBasic
from app.models.trade_calendar import TradeCalendar


@dataclass(frozen=True)
class TableSummary:
    count: int
    last_updated: datetime | None


@dataclass(frozen=True)
class HealthSummary:
    stock_basic: TableSummary
    trade_calendar: TableSummary
    k_line_daily: TableSummary
    latest_market_cap: TableSummary
    latest_task: TableSummary


def _summary_from(session: Session, model, ts_column) -> TableSummary:
    stmt = select(func.count(model.id), func.max(ts_column))
    count, last = session.execute(stmt).one()
    return TableSummary(count=int(count), last_updated=last)


def get_summary(session: Session) -> HealthSummary:
    return HealthSummary(
        stock_basic=_summary_from(session, StockBasic, StockBasic.updated_at),
        trade_calendar=_summary_from(session, TradeCalendar, TradeCalendar.updated_at),
        k_line_daily=_summary_from(session, KLineDaily, KLineDaily.updated_at),
        latest_market_cap=_summary_from(session, LatestMarketCap, LatestMarketCap.updated_at),
        latest_task=_summary_from(session, DataUpdateTask, DataUpdateTask.started_at),
    )


def summary_to_dict(summary: HealthSummary) -> dict:
    """Envelope-friendly nested dict; datetimes serialized ISO 8601."""

    def one(t: TableSummary) -> dict:
        return {
            "count": t.count,
            "last_updated": t.last_updated.isoformat() if t.last_updated else None,
        }

    return {
        "stock_basic": one(summary.stock_basic),
        "trade_calendar": one(summary.trade_calendar),
        "k_line_daily": one(summary.k_line_daily),
        "latest_market_cap": one(summary.latest_market_cap),
        "latest_task": one(summary.latest_task),
    }


__all__ = ["HealthSummary", "TableSummary", "get_summary", "summary_to_dict"]
