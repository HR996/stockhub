"""k_line_daily — 日 K 线（对齐 docs/05_DATA_MODEL.md §4.3, ADR-K01：三口径一表 3 组字段）."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, Index, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_updated_at

PRICE = Numeric(12, 4)
VOL = Numeric(20, 2)
RATE = Numeric(10, 4)


class KLineDaily(Base):
    __tablename__ = "k_line_daily"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_k_line_daily_code_date"),
        Index("ix_k_line_daily_date_code", "trade_date", "ts_code"),
        Index("ix_k_line_daily_code_date_desc", "ts_code", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    open_raw: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    high_raw: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    low_raw: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    close_raw: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    preclose_raw: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)

    open_qfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    high_qfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    low_qfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    close_qfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    preclose_qfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)

    open_hfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    high_hfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    low_hfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    close_hfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    preclose_hfq: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)

    volume: Mapped[Decimal | None] = mapped_column(VOL, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    turn: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    pct_chg: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)

    trade_status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    is_st_row: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_at: Mapped[datetime] = mapped_col_updated_at()
