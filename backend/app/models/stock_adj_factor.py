"""stock_adj_factor — authoritative Tushare factors for dynamic adjustment."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_updated_at


class StockAdjFactor(Base):
    __tablename__ = "stock_adj_factor"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_stock_adj_factor_code_date"),
        Index("ix_stock_adj_factor_date_code", "trade_date", "ts_code"),
        Index("ix_stock_adj_factor_code_date_desc", "ts_code", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    adj_factor: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="tushare")
    updated_at: Mapped[datetime] = mapped_col_updated_at()
