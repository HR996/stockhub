"""stock_adj_factor Repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.stock_adj_factor import StockAdjFactor


@dataclass(frozen=True)
class AdjFactorUpsertRow:
    ts_code: str
    trade_date: date
    adj_factor: Decimal
    source: str = "tushare"


_COLS = 4


class AdjFactorRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, rows: Iterable[AdjFactorUpsertRow]) -> int:
        payload = [row.__dict__ for row in rows]
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=_COLS):
            stmt = insert(StockAdjFactor).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[StockAdjFactor.ts_code, StockAdjFactor.trade_date],
                set_={
                    "adj_factor": stmt.excluded.adj_factor,
                    "source": stmt.excluded.source,
                },
            )
            self._session.execute(stmt)
        return len(payload)

    def list_for_stock(self, ts_code: str, start: date, end: date) -> Sequence[StockAdjFactor]:
        stmt = (
            select(StockAdjFactor)
            .where(StockAdjFactor.ts_code == ts_code)
            .where(StockAdjFactor.trade_date.between(start, end))
            .order_by(StockAdjFactor.trade_date)
        )
        return self._session.execute(stmt).scalars().all()

    def latest_for_stock(self, ts_code: str) -> StockAdjFactor | None:
        stmt = (
            select(StockAdjFactor)
            .where(StockAdjFactor.ts_code == ts_code)
            .order_by(StockAdjFactor.trade_date.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def count(self) -> int:
        return int(self._session.execute(select(func.count(StockAdjFactor.id))).scalar_one())
