"""Shenwan (SW) industry repositories — snapshot-only, TRUNCATE + INSERT on refresh.

No version concept: each `replace_all` call wipes and rewrites the entire table
in a single transaction; the outer `session_scope()` from the caller commits atomically.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.stock_basic import StockBasic
from app.models.sw_industry import SWIndustryClassify, SWIndustryMember


@dataclass(frozen=True)
class SWClassifyRecord:
    index_code: str
    industry_code: str
    industry_name: str
    level: str
    parent_code: str | None
    is_pub: bool | None
    src: str


@dataclass(frozen=True)
class SWMemberRecord:
    ts_code: str
    l1_index_code: str
    l1_name: str
    l2_index_code: str
    l2_name: str
    l3_index_code: str
    l3_name: str
    in_date: date | None
    out_date: date | None


_CLASSIFY_COLS = 7
_MEMBER_COLS = 9


class SWClassifyRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_all(self, rows: Iterable[SWClassifyRecord]) -> int:
        """DELETE all rows and bulk-insert the new snapshot in the current transaction.

        We use DELETE rather than TRUNCATE so the operation composes with the
        surrounding transaction (TRUNCATE has surprising interactions with
        SQLAlchemy sessions and referential integrity checks).
        """
        payload = [r.__dict__ for r in rows]
        self._session.execute(delete(SWIndustryClassify))
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=_CLASSIFY_COLS):
            self._session.execute(insert(SWIndustryClassify).values(batch))
        return len(payload)

    def list_all(self) -> Sequence[SWIndustryClassify]:
        stmt = select(SWIndustryClassify).order_by(
            SWIndustryClassify.level, SWIndustryClassify.index_code
        )
        return self._session.execute(stmt).scalars().all()

    def list_by_level(self, level: str) -> Sequence[SWIndustryClassify]:
        stmt = (
            select(SWIndustryClassify)
            .where(SWIndustryClassify.level == level)
            .order_by(SWIndustryClassify.index_code)
        )
        return self._session.execute(stmt).scalars().all()

    def get_by_index_code(self, index_code: str) -> SWIndustryClassify | None:
        stmt = select(SWIndustryClassify).where(SWIndustryClassify.index_code == index_code)
        return self._session.execute(stmt).scalar_one_or_none()

    def count(self) -> int:
        return len(list(self._session.execute(select(SWIndustryClassify.id)).scalars().all()))


class SWMemberRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_all(self, rows: Iterable[SWMemberRecord]) -> int:
        payload = [r.__dict__ for r in rows]
        self._session.execute(delete(SWIndustryMember))
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=_MEMBER_COLS):
            self._session.execute(insert(SWIndustryMember).values(batch))
        return len(payload)

    def get_by_ts_code(self, ts_code: str) -> SWIndustryMember | None:
        stmt = select(SWIndustryMember).where(SWIndustryMember.ts_code == ts_code)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_l2_index_code(self, l2_index_code: str) -> Sequence[SWIndustryMember]:
        stmt = (
            select(SWIndustryMember)
            .where(SWIndustryMember.l2_index_code == l2_index_code)
            .order_by(SWIndustryMember.ts_code)
        )
        return self._session.execute(stmt).scalars().all()

    def list_by_l3_index_code(self, l3_index_code: str) -> Sequence[SWIndustryMember]:
        stmt = (
            select(SWIndustryMember)
            .where(SWIndustryMember.l3_index_code == l3_index_code)
            .order_by(SWIndustryMember.ts_code)
        )
        return self._session.execute(stmt).scalars().all()

    def list_stocks_by_node(
        self, level: str, index_code: str
    ) -> Sequence[tuple[SWIndustryMember, str | None]]:
        """List (member, stock_name) pairs under a given L1/L2/L3 node.

        `stock_name` is joined from `stock_basic.name` (LEFT JOIN, so members
        whose ts_code isn't in stock_basic yet still appear with name=None).
        """
        col_map = {
            "L1": SWIndustryMember.l1_index_code,
            "L2": SWIndustryMember.l2_index_code,
            "L3": SWIndustryMember.l3_index_code,
        }
        col = col_map.get(level)
        if col is None:
            raise ValueError(f"invalid level {level!r}; expected L1/L2/L3")
        stmt = (
            select(SWIndustryMember, StockBasic.name)
            .join(StockBasic, StockBasic.ts_code == SWIndustryMember.ts_code, isouter=True)
            .where(col == index_code)
            .order_by(SWIndustryMember.ts_code)
        )
        return list(self._session.execute(stmt).all())

    def count(self) -> int:
        return len(list(self._session.execute(select(SWIndustryMember.id)).scalars().all()))
