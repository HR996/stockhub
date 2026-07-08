"""latest_market_cap Repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.latest_market_cap import LatestMarketCap


@dataclass(frozen=True)
class MarketCapUpsertRow:
    ts_code: str
    market_cap_source: str
    total_market_cap: Decimal | None = None
    circ_market_cap: Decimal | None = None
    total_share: Decimal | None = None
    liqa_share: Decimal | None = None
    snapshot_close: Decimal | None = None
    snapshot_date: date | None = None
    snapshot_at: datetime | None = None


_COLS = 9


class MarketCapRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, rows: Iterable[MarketCapUpsertRow]) -> int:
        payload = [
            {k: v for k, v in row.__dict__.items() if not (k == "snapshot_at" and v is None)}
            for row in rows
        ]
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=_COLS):
            stmt = insert(LatestMarketCap).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[LatestMarketCap.ts_code],
                set_={
                    "total_market_cap": stmt.excluded.total_market_cap,
                    "circ_market_cap": stmt.excluded.circ_market_cap,
                    "total_share": stmt.excluded.total_share,
                    "liqa_share": stmt.excluded.liqa_share,
                    "snapshot_close": stmt.excluded.snapshot_close,
                    "snapshot_date": stmt.excluded.snapshot_date,
                    "market_cap_source": stmt.excluded.market_cap_source,
                    "snapshot_at": stmt.excluded.snapshot_at,
                },
            )
            self._session.execute(stmt)
        return len(payload)

    def get_by_ts_code(self, ts_code: str) -> LatestMarketCap | None:
        return self._session.execute(
            select(LatestMarketCap).where(LatestMarketCap.ts_code == ts_code)
        ).scalar_one_or_none()

    def count(self) -> int:
        return int(self._session.execute(select(func.count(LatestMarketCap.id))).scalar_one())

    def count_missing(self) -> int:
        stmt = select(func.count(LatestMarketCap.id)).where(
            LatestMarketCap.total_market_cap.is_(None)
        )
        return int(self._session.execute(stmt).scalar_one())

    def list_all(self) -> Sequence[LatestMarketCap]:
        return (
            self._session.execute(select(LatestMarketCap).order_by(LatestMarketCap.ts_code))
            .scalars()
            .all()
        )
