"""Factor result/config models for SW sector momentum."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_created_at, mapped_col_updated_at


class FactorConfig(Base):
    __tablename__ = "factor_config"
    __table_args__ = (
        UniqueConstraint("name", "owner", name="uq_factor_config_name_owner"),
        Index("ix_factor_config_owner_updated", "owner", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_col_created_at()
    updated_at: Mapped[datetime] = mapped_col_updated_at()
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)


class FactorResult(Base):
    __tablename__ = "factor_result"
    __table_args__ = (
        Index("ix_factor_result_created", "created_at"),
        Index("ix_factor_result_basedate_created", "basedate", "created_at"),
        Index("ix_factor_result_class_basedate", "classification", "basedate"),
        Index("ix_factor_result_stale", "stale"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    basedate: Mapped[date] = mapped_column(Date, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    industry_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stale_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)


class FactorResultRow(Base):
    __tablename__ = "factor_result_row"
    __table_args__ = (
        UniqueConstraint("result_id", "level", "sector_code", name="uq_factor_row_result_level_sector"),
        Index("ix_factor_row_result_level_score", "result_id", "level", "momentum_score"),
        Index("ix_factor_row_result_parent", "result_id", "parent_sector_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(
        ForeignKey("factor_result.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[str] = mapped_column(String(4), nullable=False)
    sector_code: Mapped[str] = mapped_column(String(32), nullable=False)
    sector_name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_sector_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sector_stock_count: Mapped[int] = mapped_column(nullable=False)
    sector_top_stock_count: Mapped[int] = mapped_column(nullable=False)
    top_density: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    median_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    momentum_score: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    small_sample_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FactorResultStock(Base):
    __tablename__ = "factor_result_stock"
    __table_args__ = (
        UniqueConstraint("result_id", "ts_code", name="uq_factor_stock_result_ts_code"),
        Index("ix_factor_stock_result_l1_return", "result_id", "l1_code", "stock_return"),
        Index("ix_factor_stock_result_l2_return", "result_id", "l2_code", "stock_return"),
        Index("ix_factor_stock_result_l3_return", "result_id", "l3_code", "stock_return"),
        Index("ix_factor_stock_result_top", "result_id", "is_top"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(
        ForeignKey("factor_result.id", ondelete="CASCADE"), nullable=False
    )
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(64), nullable=False)
    l1_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    l1_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    l2_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    l2_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    l3_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    l3_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stock_return: Mapped[Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)
    is_top: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    missing_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
