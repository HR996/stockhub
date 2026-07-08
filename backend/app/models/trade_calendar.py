"""trade_calendar — 交易日历（对齐 docs/05_DATA_MODEL.md §4.2）."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_updated_at


class TradeCalendar(Base):
    __tablename__ = "trade_calendar"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cal_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_col_updated_at()
