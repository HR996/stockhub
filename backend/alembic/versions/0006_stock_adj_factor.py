"""add stock_adj_factor

Revision ID: 41f0e646d2f7
Revises: 8a7f40bc2b3d
Create Date: 2026-07-08 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "41f0e646d2f7"
down_revision: str | Sequence[str] | None = "8a7f40bc2b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stock_adj_factor",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("adj_factor", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ts_code", "trade_date", name="uq_stock_adj_factor_code_date"),
    )
    op.create_index("ix_stock_adj_factor_code_date_desc", "stock_adj_factor", ["ts_code", "trade_date"], unique=False)
    op.create_index("ix_stock_adj_factor_date_code", "stock_adj_factor", ["trade_date", "ts_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stock_adj_factor_date_code", table_name="stock_adj_factor")
    op.drop_index("ix_stock_adj_factor_code_date_desc", table_name="stock_adj_factor")
    op.drop_table("stock_adj_factor")
