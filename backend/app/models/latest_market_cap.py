"""latest_market_cap — 最新市值（对齐 docs/05_DATA_MODEL.md §4.4）.

数据源：baostock。合成公式 = 最新一期 `totalShare` × 快照日 `close_raw`。
- `total_market_cap` = total_share × close_raw
- `circ_market_cap`  = liqa_share × close_raw
- `market_cap_source` ∈ {`baostock_synth`, `baostock_missing`}
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_updated_at


class LatestMarketCap(Base):
    __tablename__ = "latest_market_cap"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    total_market_cap: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    circ_market_cap: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    liqa_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    snapshot_close: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    snapshot_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    market_cap_source: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_col_updated_at()
    updated_at: Mapped[datetime] = mapped_col_updated_at()

