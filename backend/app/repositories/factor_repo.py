"""Repositories for factor configs and persisted SW momentum results."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.db import chunked
from app.models.factor import FactorConfig, FactorResult, FactorResultRow, FactorResultStock


@dataclass(frozen=True)
class FactorResultCreate:
    params: dict[str, Any]
    basedate: date
    start_date: date
    classification: str
    industry_snapshot_at: datetime | None
    created_by: str


@dataclass(frozen=True)
class FactorRowCreate:
    result_id: int
    level: str
    sector_code: str
    sector_name: str
    parent_sector_code: str | None
    sector_stock_count: int
    sector_top_stock_count: int
    top_density: Decimal
    median_return: Decimal | None
    momentum_score: Decimal
    small_sample_flag: bool


@dataclass(frozen=True)
class FactorStockCreate:
    result_id: int
    ts_code: str
    stock_name: str
    l1_code: str | None
    l1_name: str | None
    l2_code: str | None
    l2_name: str | None
    l3_code: str | None
    l3_name: str | None
    stock_return: Decimal | None
    is_top: bool
    missing_reason: str | None


class FactorResultRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, row: FactorResultCreate) -> FactorResult:
        obj = FactorResult(**row.__dict__)
        self._session.add(obj)
        self._session.flush()
        return obj

    def insert_rows(self, rows: Iterable[FactorRowCreate]) -> int:
        payload = [r.__dict__ for r in rows]
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=11):
            self._session.bulk_insert_mappings(FactorResultRow, batch)
        return len(payload)

    def insert_stocks(self, rows: Iterable[FactorStockCreate]) -> int:
        payload = [r.__dict__ for r in rows]
        if not payload:
            return 0
        for batch in chunked(payload, columns_per_row=13):
            self._session.bulk_insert_mappings(FactorResultStock, batch)
        return len(payload)

    def get(self, result_id: int) -> FactorResult | None:
        return self._session.get(FactorResult, result_id)

    def list_results(self, limit: int = 50) -> list[FactorResult]:
        stmt = select(FactorResult).order_by(FactorResult.created_at.desc()).limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def rows_by_level(self, result_id: int, level: str) -> list[FactorResultRow]:
        stmt = (
            select(FactorResultRow)
            .where(FactorResultRow.result_id == result_id, FactorResultRow.level == level)
            .order_by(FactorResultRow.momentum_score.desc(), FactorResultRow.sector_code)
        )
        return list(self._session.execute(stmt).scalars().all())

    def child_rows(
        self, result_id: int, parent_sector_code: str, child_level: str
    ) -> list[FactorResultRow]:
        stmt = (
            select(FactorResultRow)
            .where(
                FactorResultRow.result_id == result_id,
                FactorResultRow.level == child_level,
                FactorResultRow.parent_sector_code == parent_sector_code,
            )
            .order_by(FactorResultRow.momentum_score.desc(), FactorResultRow.sector_code)
        )
        return list(self._session.execute(stmt).scalars().all())

    def sector_stocks(self, result_id: int, level: str, sector_code: str) -> list[FactorResultStock]:
        col = {
            "L1": FactorResultStock.l1_code,
            "L2": FactorResultStock.l2_code,
            "L3": FactorResultStock.l3_code,
        }[level]
        stmt = (
            select(FactorResultStock)
            .where(FactorResultStock.result_id == result_id, col == sector_code)
            .order_by(FactorResultStock.stock_return.desc().nullslast(), FactorResultStock.ts_code)
        )
        return list(self._session.execute(stmt).scalars().all())

    def mark_sw_stale_before(self, snapshot_at: datetime, reason: str = "INDUSTRY_UPDATE") -> int:
        stmt = (
            update(FactorResult)
            .where(
                FactorResult.classification == "SW",
                FactorResult.stale.is_(False),
                FactorResult.industry_snapshot_at.is_not(None),
                FactorResult.industry_snapshot_at < snapshot_at,
            )
            .values(stale=True, stale_reason=reason, stale_at=datetime.now(UTC))
        )
        result = self._session.execute(stmt)
        return int(result.rowcount or 0)


class FactorConfigRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_owner(self, owner: str) -> list[FactorConfig]:
        stmt = (
            select(FactorConfig)
            .where(FactorConfig.owner == owner)
            .order_by(FactorConfig.updated_at.desc(), FactorConfig.id.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def create(self, name: str, params: dict[str, Any], owner: str) -> FactorConfig:
        obj = FactorConfig(name=name, params=params, owner=owner, updated_by=owner)
        self._session.add(obj)
        self._session.flush()
        return obj

    def get_for_owner(self, config_id: int, owner: str) -> FactorConfig | None:
        stmt = select(FactorConfig).where(FactorConfig.id == config_id, FactorConfig.owner == owner)
        return self._session.execute(stmt).scalar_one_or_none()

    def update(
        self,
        config_id: int,
        owner: str,
        *,
        name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> FactorConfig | None:
        obj = self.get_for_owner(config_id, owner)
        if obj is None:
            return None
        if name is not None:
            obj.name = name
        if params is not None:
            obj.params = params
        obj.updated_by = owner
        self._session.flush()
        return obj

    def delete(self, config_id: int, owner: str) -> bool:
        result = self._session.execute(
            delete(FactorConfig).where(FactorConfig.id == config_id, FactorConfig.owner == owner)
        )
        return bool(result.rowcount)
