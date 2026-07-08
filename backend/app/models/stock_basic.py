"""stock_basic — 股票基础信息（对齐 docs/05_DATA_MODEL.md §4.1）."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_updated_at


class StockBasic(Base):
    __tablename__ = "stock_basic"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    bs_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delist_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_bj: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_common: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_st: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_col_updated_at()
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
