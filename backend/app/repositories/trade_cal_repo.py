"""trade_calendar Repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.trade_calendar import TradeCalendar


@dataclass(frozen=True)
class TradeCalRow:
    cal_date: date
    is_open: bool


_COLS = 2


class TradeCalRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(self, rows: Iterable[TradeCalRow]) -> int:
        payload = [row.__dict__ for row in rows]
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=_COLS):
            stmt = insert(TradeCalendar).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[TradeCalendar.cal_date],
                set_={"is_open": stmt.excluded.is_open},
            )
            self._session.execute(stmt)
        return len(payload)

    def is_trading_day(self, day: date) -> bool:
        result = self._session.execute(
            select(TradeCalendar.is_open).where(TradeCalendar.cal_date == day)
        ).scalar_one_or_none()
        return bool(result)

    def previous_trading_days(self, base: date, count: int) -> list[date]:
        """Return the `count` most recent trading days on or before `base`, oldest first."""
        stmt = (
            select(TradeCalendar.cal_date)
            .where(TradeCalendar.is_open.is_(True))
            .where(TradeCalendar.cal_date <= base)
            .order_by(TradeCalendar.cal_date.desc())
            .limit(count)
        )
        result = list(self._session.execute(stmt).scalars().all())
        return list(reversed(result))

    def count(self) -> int:
        return int(self._session.execute(select(func.count(TradeCalendar.id))).scalar_one())

    def list_range(self, start: date, end: date) -> Sequence[TradeCalendar]:
        stmt = (
            select(TradeCalendar)
            .where(TradeCalendar.cal_date.between(start, end))
            .order_by(TradeCalendar.cal_date)
        )
        return self._session.execute(stmt).scalars().all()
