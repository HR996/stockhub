"""Repository and rebuild operations for the latest-basedate QFQ cache."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.k_line_daily import KLineDaily
from app.models.k_line_qfq_latest import KLineQfqLatest
from app.models.stock_adj_factor import StockAdjFactor

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class QfqCacheRow:
    ts_code: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    preclose: Decimal | None
    base_date: date
    base_adj_factor: Decimal
    calculated_at: datetime


class QfqCacheRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_stock(self, ts_code: str, rows: Iterable[QfqCacheRow]) -> int:
        payload = [asdict(row) for row in rows]
        self._session.execute(
            delete(KLineQfqLatest).where(KLineQfqLatest.ts_code == ts_code)
        )
        for batch in chunked(payload, columns_per_row=10):
            self._session.execute(insert(KLineQfqLatest).values(batch))
        return len(payload)

    def upsert_many(self, rows: Iterable[QfqCacheRow]) -> int:
        payload = [asdict(row) for row in rows]
        for batch in chunked(payload, columns_per_row=10):
            stmt = insert(KLineQfqLatest).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[KLineQfqLatest.ts_code, KLineQfqLatest.trade_date],
                set_={
                    column: stmt.excluded[column]
                    for column in (
                        "open", "high", "low", "close", "preclose",
                        "base_date", "base_adj_factor", "calculated_at",
                    )
                },
            )
            self._session.execute(stmt)
        return len(payload)

    def list_by_stock(
        self, ts_code: str, start: date, end: date
    ) -> Sequence[KLineQfqLatest]:
        return self._session.execute(
            select(KLineQfqLatest)
            .where(KLineQfqLatest.ts_code == ts_code)
            .where(KLineQfqLatest.trade_date.between(start, end))
            .order_by(KLineQfqLatest.trade_date)
        ).scalars().all()

    def latest_for_stock(self, ts_code: str) -> KLineQfqLatest | None:
        return self._session.execute(
            select(KLineQfqLatest)
            .where(KLineQfqLatest.ts_code == ts_code)
            .order_by(KLineQfqLatest.trade_date.desc())
            .limit(1)
        ).scalar_one_or_none()

    def count_for_stock(self, ts_code: str) -> int:
        return int(self._session.execute(
            select(func.count(KLineQfqLatest.id))
            .where(KLineQfqLatest.ts_code == ts_code)
        ).scalar_one())


def rebuild_qfq_for_stock(session: Session, ts_code: str) -> int:
    latest_factor = session.execute(
        select(StockAdjFactor)
        .where(StockAdjFactor.ts_code == ts_code)
        .order_by(StockAdjFactor.trade_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    repo = QfqCacheRepo(session)
    if latest_factor is None or latest_factor.adj_factor == 0:
        return repo.replace_stock(ts_code, [])

    stmt = (
        select(KLineDaily, StockAdjFactor.adj_factor)
        .join(
            StockAdjFactor,
            (StockAdjFactor.ts_code == KLineDaily.ts_code)
            & (StockAdjFactor.trade_date == KLineDaily.trade_date),
        )
        .where(KLineDaily.ts_code == ts_code)
        .order_by(KLineDaily.trade_date)
    )
    now = datetime.now(UTC)
    rows = [
        QfqCacheRow(
            ts_code=bar.ts_code,
            trade_date=bar.trade_date,
            open=_qfq(bar.open_raw, factor, latest_factor.adj_factor),
            high=_qfq(bar.high_raw, factor, latest_factor.adj_factor),
            low=_qfq(bar.low_raw, factor, latest_factor.adj_factor),
            close=_qfq(bar.close_raw, factor, latest_factor.adj_factor),
            preclose=_qfq(bar.preclose_raw, factor, latest_factor.adj_factor),
            base_date=latest_factor.trade_date,
            base_adj_factor=latest_factor.adj_factor,
            calculated_at=now,
        )
        for bar, factor in session.execute(stmt).all()
    ]
    return repo.replace_stock(ts_code, rows)


def rebuild_qfq_cache(
    session: Session, ts_codes: Iterable[str] | None = None
) -> tuple[int, int]:
    codes = list(ts_codes) if ts_codes is not None else list(
        session.execute(
            select(KLineDaily.ts_code).distinct().order_by(KLineDaily.ts_code)
        ).scalars()
    )
    rows = 0
    total = len(codes)
    for index, code in enumerate(codes, start=1):
        rows += rebuild_qfq_for_stock(session, code)
        if index == 1 or index % 100 == 0 or index == total:
            logger.info(
                "QFQ cache progress: %d/%d stocks, %d rows", index, total, rows
            )
    return len(codes), rows


def refresh_qfq_cache_for_day(
    session: Session, trade_date: date, ts_codes: Iterable[str]
) -> tuple[int, int]:
    """Incrementally refresh one day; rebuild stocks whose base factor changed."""
    codes = sorted(set(ts_codes))
    if not codes:
        return 0, 0
    latest_factors = {
        code: (factor_date, factor)
        for code, factor_date, factor in session.execute(
            select(
                StockAdjFactor.ts_code,
                StockAdjFactor.trade_date,
                StockAdjFactor.adj_factor,
            )
            .distinct(StockAdjFactor.ts_code)
            .where(StockAdjFactor.ts_code.in_(codes))
            .order_by(StockAdjFactor.ts_code, StockAdjFactor.trade_date.desc())
        ).all()
    }
    cached_bases = {
        code: (base_date, base_factor)
        for code, base_date, base_factor in session.execute(
            select(
                KLineQfqLatest.ts_code,
                KLineQfqLatest.base_date,
                KLineQfqLatest.base_adj_factor,
            )
            .distinct(KLineQfqLatest.ts_code)
            .where(KLineQfqLatest.ts_code.in_(codes))
            .order_by(KLineQfqLatest.ts_code, KLineQfqLatest.trade_date.desc())
        ).all()
    }
    rebuild_codes = {
        code
        for code in codes
        if code in latest_factors
        and (
            code not in cached_bases
            or cached_bases[code][1] != latest_factors[code][1]
        )
    }
    rebuilt_rows = sum(rebuild_qfq_for_stock(session, code) for code in rebuild_codes)

    incremental_codes = set(codes) - rebuild_codes
    stmt = (
        select(KLineDaily, StockAdjFactor.adj_factor)
        .join(
            StockAdjFactor,
            (StockAdjFactor.ts_code == KLineDaily.ts_code)
            & (StockAdjFactor.trade_date == KLineDaily.trade_date),
        )
        .where(KLineDaily.trade_date == trade_date)
        .where(KLineDaily.ts_code.in_(incremental_codes))
    )
    now = datetime.now(UTC)
    incremental_rows: list[QfqCacheRow] = []
    for bar, factor in session.execute(stmt).all():
        base = latest_factors.get(bar.ts_code)
        if base is None:
            continue
        base_date, base_factor = base
        incremental_rows.append(
            QfqCacheRow(
                ts_code=bar.ts_code,
                trade_date=bar.trade_date,
                open=_qfq(bar.open_raw, factor, base_factor),
                high=_qfq(bar.high_raw, factor, base_factor),
                low=_qfq(bar.low_raw, factor, base_factor),
                close=_qfq(bar.close_raw, factor, base_factor),
                preclose=_qfq(bar.preclose_raw, factor, base_factor),
                base_date=base_date,
                base_adj_factor=base_factor,
                calculated_at=now,
            )
        )
    incremental_written = QfqCacheRepo(session).upsert_many(incremental_rows)
    return len(rebuild_codes), rebuilt_rows + incremental_written


def _qfq(
    price: Decimal | None, factor: Decimal, base_factor: Decimal
) -> Decimal | None:
    if price is None or base_factor == 0:
        return None
    return price * factor / base_factor
