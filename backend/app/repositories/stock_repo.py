"""stock_basic Repository — 领域方法，不返回 ORM Query。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.stock_basic import StockBasic


@dataclass(frozen=True)
class StockBasicRow:
    ts_code: str
    bs_code: str
    name: str
    market: str
    list_date: date | None = None
    delist_date: date | None = None
    is_bj: bool = False
    is_common: bool = True
    is_st: bool = False
    updated_by: str | None = None


_COLS = 10  # keep in sync with StockBasicRow field count


class StockBasicRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, rows: Iterable[StockBasicRow]) -> int:
        """Idempotent bulk upsert on `ts_code`. Chunks to respect PG param limits."""
        payload = [row.__dict__ for row in rows]
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=_COLS):
            stmt = insert(StockBasic).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[StockBasic.ts_code],
                set_={
                    "bs_code": stmt.excluded.bs_code,
                    "name": stmt.excluded.name,
                    "market": stmt.excluded.market,
                    "list_date": stmt.excluded.list_date,
                    "delist_date": stmt.excluded.delist_date,
                    "is_bj": stmt.excluded.is_bj,
                    "is_common": stmt.excluded.is_common,
                    "is_st": stmt.excluded.is_st,
                    "updated_by": stmt.excluded.updated_by,
                },
            )
            self._session.execute(stmt)
        return len(payload)

    def get_by_ts_code(self, ts_code: str) -> StockBasic | None:
        return self._session.execute(
            select(StockBasic).where(StockBasic.ts_code == ts_code)
        ).scalar_one_or_none()

    def count(self) -> int:
        return int(self._session.execute(select(func.count(StockBasic.id))).scalar_one())

    def count_active_at(self, day: date) -> int:
        """Common stocks live on `day`: is_common AND list_date<=day AND (delist NULL OR >day)."""
        stmt = select(func.count(StockBasic.id)).where(
            StockBasic.is_common.is_(True),
            StockBasic.list_date.is_not(None),
            StockBasic.list_date <= day,
            or_(StockBasic.delist_date.is_(None), StockBasic.delist_date > day),
        )
        return int(self._session.execute(stmt).scalar_one())

    def list_active_ts_codes_at(self, day: date) -> list[str]:
        """ts_codes of common stocks live on `day`."""
        stmt = (
            select(StockBasic.ts_code)
            .where(
                StockBasic.is_common.is_(True),
                StockBasic.list_date.is_not(None),
                StockBasic.list_date <= day,
                or_(StockBasic.delist_date.is_(None), StockBasic.delist_date > day),
            )
            .order_by(StockBasic.ts_code)
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_all(self) -> Sequence[StockBasic]:
        return self._session.execute(select(StockBasic).order_by(StockBasic.ts_code)).scalars().all()
