"""k_line_daily Repository."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.k_line_daily import KLineDaily
from app.models.stock_basic import StockBasic

_UPSERT_COLUMNS: tuple[str, ...] = (
    "open_raw", "high_raw", "low_raw", "close_raw", "preclose_raw",
    "trade_status", "is_st_row", "volume", "amount", "turn", "pct_chg",
)


@dataclass(frozen=True)
class KLineRow:
    ts_code: str
    trade_date: date
    trade_status: int = 1
    is_st_row: bool = False

    open_raw: Decimal | None = None
    high_raw: Decimal | None = None
    low_raw: Decimal | None = None
    close_raw: Decimal | None = None
    preclose_raw: Decimal | None = None

    volume: Decimal | None = None
    amount: Decimal | None = None
    turn: Decimal | None = None
    pct_chg: Decimal | None = None


_COLS = 13


class KLineRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_many(
        self,
        rows: Iterable[KLineRow],
    ) -> int:
        """Idempotently upsert canonical unadjusted rows."""
        payload = [asdict(r) for r in rows]
        if not payload:
            return 0

        for batch in chunked(payload, columns_per_row=_COLS):
            stmt = insert(KLineDaily).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[KLineDaily.ts_code, KLineDaily.trade_date],
                set_={col: stmt.excluded[col] for col in _UPSERT_COLUMNS},
            )
            self._session.execute(stmt)
        return len(payload)

    def get(self, ts_code: str, trade_date: date) -> KLineDaily | None:
        stmt = select(KLineDaily).where(
            KLineDaily.ts_code == ts_code, KLineDaily.trade_date == trade_date
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_stock(
        self, ts_code: str, start: date, end: date
    ) -> Sequence[KLineDaily]:
        stmt = (
            select(KLineDaily)
            .where(KLineDaily.ts_code == ts_code)
            .where(KLineDaily.trade_date.between(start, end))
            .order_by(KLineDaily.trade_date)
        )
        return self._session.execute(stmt).scalars().all()

    def count_by_date(self, trade_date: date) -> int:
        return int(
            self._session.execute(
                select(func.count(KLineDaily.id)).where(KLineDaily.trade_date == trade_date)
            ).scalar_one()
        )

    def distinct_stock_counts_by_date_range(
        self, start: date, end: date
    ) -> dict[date, int]:
        """Return {trade_date: distinct common-stock ts_code count} across [start, end].

        Only counts rows whose ts_code belongs to a common stock (is_common=True).
        This keeps the denominator consistent with count_active_at() in StockBasicRepo,
        preventing index codes stored in k_line_daily from inflating the actual count.
        """
        stmt = (
            select(
                KLineDaily.trade_date,
                func.count(func.distinct(KLineDaily.ts_code)),
            )
            .join(StockBasic, StockBasic.ts_code == KLineDaily.ts_code)
            .where(StockBasic.is_common.is_(True))
            .where(KLineDaily.trade_date.between(start, end))
            .group_by(KLineDaily.trade_date)
        )
        return {row[0]: int(row[1]) for row in self._session.execute(stmt).all()}

    def anomaly_dates_in_range(self, start: date, end: date) -> set[date]:
        """Trade dates in [start, end] with at least one anomalous common-stock row.

        Anomaly = trade_status != 0 (not suspended) but close_raw is NULL.
        """
        stmt = (
            select(func.distinct(KLineDaily.trade_date))
            .join(StockBasic, StockBasic.ts_code == KLineDaily.ts_code)
            .where(StockBasic.is_common.is_(True))
            .where(KLineDaily.trade_date.between(start, end))
            .where(KLineDaily.trade_status != 0)
            .where(KLineDaily.close_raw.is_(None))
        )
        return {row[0] for row in self._session.execute(stmt).all()}

    def ts_codes_on(self, day: date) -> set[str]:
        """Distinct common-stock ts_codes with a row on `day`."""
        stmt = (
            select(func.distinct(KLineDaily.ts_code))
            .join(StockBasic, StockBasic.ts_code == KLineDaily.ts_code)
            .where(StockBasic.is_common.is_(True))
            .where(KLineDaily.trade_date == day)
        )
        return {row[0] for row in self._session.execute(stmt).all()}

    def anomaly_ts_codes_on(self, day: date) -> set[str]:
        """Common-stock ts_codes on `day` where trade_status != 0 but close_raw is NULL."""
        stmt = (
            select(func.distinct(KLineDaily.ts_code))
            .join(StockBasic, StockBasic.ts_code == KLineDaily.ts_code)
            .where(StockBasic.is_common.is_(True))
            .where(KLineDaily.trade_date == day)
            .where(KLineDaily.trade_status != 0)
            .where(KLineDaily.close_raw.is_(None))
        )
        return {row[0] for row in self._session.execute(stmt).all()}

    def count(self) -> int:
        return int(self._session.execute(select(func.count(KLineDaily.id))).scalar_one())

    def latest_trade_date(self) -> date | None:
        return self._session.execute(select(func.max(KLineDaily.trade_date))).scalar_one()
