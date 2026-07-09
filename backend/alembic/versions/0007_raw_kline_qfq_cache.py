"""store raw K-lines only and add latest-basedate QFQ cache

Revision ID: a712c84f9301
Revises: 41f0e646d2f7

This migration intentionally clears market data. Re-run the Tushare initializer
after upgrading. Downgrade restores the old nullable columns, not deleted data.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a712c84f9301"
down_revision: str | Sequence[str] | None = "41f0e646d2f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM factor_result")
    op.execute("TRUNCATE TABLE latest_market_cap, stock_adj_factor, k_line_daily RESTART IDENTITY")
    op.execute(
        """
        DELETE FROM data_update_task
        WHERE task_type IN (
            'TUSHARE_INIT',
            'TUSHARE_UPDATE_DAILY',
            'TUSHARE_QFQ_CACHE',
            'TUSHARE_RECOMPUTE_ADJUSTED'
        )
        """
    )

    for prefix in ("open", "high", "low", "close", "preclose"):
        op.drop_column("k_line_daily", f"{prefix}_qfq")
        op.drop_column("k_line_daily", f"{prefix}_hfq")

    op.create_table(
        "k_line_qfq_latest",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("high", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("low", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("preclose", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("base_date", sa.Date(), nullable=False),
        sa.Column("base_adj_factor", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ts_code", "trade_date", name="uq_k_line_qfq_latest_code_date"
        ),
    )
    op.create_index(
        "ix_k_line_qfq_latest_code_date_desc",
        "k_line_qfq_latest",
        ["ts_code", "trade_date"],
    )
    op.create_index(
        "ix_k_line_qfq_latest_date_code",
        "k_line_qfq_latest",
        ["trade_date", "ts_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_k_line_qfq_latest_date_code", table_name="k_line_qfq_latest"
    )
    op.drop_index(
        "ix_k_line_qfq_latest_code_date_desc", table_name="k_line_qfq_latest"
    )
    op.drop_table("k_line_qfq_latest")

    for prefix in ("open", "high", "low", "close", "preclose"):
        op.add_column(
            "k_line_daily",
            sa.Column(f"{prefix}_qfq", sa.Numeric(12, 4), nullable=True),
        )
        op.add_column(
            "k_line_daily",
            sa.Column(f"{prefix}_hfq", sa.Numeric(12, 4), nullable=True),
        )
