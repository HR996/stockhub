"""Shenwan (SW) industry classification models — SW2021 catalog + stock membership.

Sourced from Tushare Pro (`pro.index_classify` + `pro.index_member_all`). No version
concept — the two tables hold a single current snapshot, refreshed weekly by the
scheduler with TRUNCATE + INSERT semantics.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_created_at


class SWIndustryClassify(Base):
    """SW2021 L1/L2/L3 catalog — one row per industry index.

    `industry_code` is the business code referenced by children's `parent_code`.
    `index_code` is the exchange-style index code (e.g. `801010.SI`).
    """

    __tablename__ = "sw_industry_classify"
    __table_args__ = (
        Index("ix_sw_industry_classify_level", "level"),
        Index("ix_sw_industry_classify_parent_code", "parent_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    index_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    industry_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    industry_name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(4), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_pub: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    src: Mapped[str] = mapped_column(String(16), nullable=False, default="SW2021")
    created_at: Mapped[datetime] = mapped_col_created_at()


class SWIndustryMember(Base):
    """Stock → SW L1/L2/L3 assignment (denormalized for cheap lookup).

    One row per stock. Only current members (`is_new='Y'` in Tushare) are stored;
    `out_date` should always be NULL here.
    """

    __tablename__ = "sw_industry_member"
    __table_args__ = (
        Index("ix_sw_industry_member_l1", "l1_index_code"),
        Index("ix_sw_industry_member_l2", "l2_index_code"),
        Index("ix_sw_industry_member_l3", "l3_index_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    l1_index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    l1_name: Mapped[str] = mapped_column(String(128), nullable=False)
    l2_index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    l2_name: Mapped[str] = mapped_column(String(128), nullable=False)
    l3_index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    l3_name: Mapped[str] = mapped_column(String(128), nullable=False)
    in_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    out_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_col_created_at()
