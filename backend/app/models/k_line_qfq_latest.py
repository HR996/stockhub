"""Latest-basedate forward-adjusted K-line display cache."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

PRICE = Numeric(18, 6)


class KLineQfqLatest(Base):
    __tablename__ = "k_line_qfq_latest"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_k_line_qfq_latest_code_date"),
        Index("ix_k_line_qfq_latest_code_date_desc", "ts_code", "trade_date"),
        Index("ix_k_line_qfq_latest_date_code", "trade_date", "ts_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    high: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    low: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    close: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    preclose: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    base_date: Mapped[date] = mapped_column(Date, nullable=False)
    base_adj_factor: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
