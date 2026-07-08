"""add browse history and factor tables

Revision ID: 8a7f40bc2b3d
Revises: 0c8e21f4a900
Create Date: 2026-07-08 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8a7f40bc2b3d"
down_revision: str | Sequence[str] | None = "0c8e21f4a900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "browse_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("page_key", sa.String(length=64), nullable=False),
        sa.Column("page_title", sa.String(length=255), nullable=False),
        sa.Column("page_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("visited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_browse_history_user_visited", "browse_history", ["username", "visited_at"], unique=False)
    op.create_index("ix_browse_history_user_key_visited", "browse_history", ["username", "page_key", "visited_at"], unique=False)

    op.create_table(
        "factor_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("owner", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "owner", name="uq_factor_config_name_owner"),
    )
    op.create_index("ix_factor_config_owner_updated", "factor_config", ["owner", "updated_at"], unique=False)

    op.create_table(
        "factor_result",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("basedate", sa.Date(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("classification", sa.String(length=16), nullable=False),
        sa.Column("industry_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stale_reason", sa.String(length=64), nullable=True),
        sa.Column("stale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_factor_result_basedate_created", "factor_result", ["basedate", "created_at"], unique=False)
    op.create_index("ix_factor_result_class_basedate", "factor_result", ["classification", "basedate"], unique=False)
    op.create_index("ix_factor_result_created", "factor_result", ["created_at"], unique=False)
    op.create_index("ix_factor_result_stale", "factor_result", ["stale"], unique=False)

    op.create_table(
        "factor_result_row",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=4), nullable=False),
        sa.Column("sector_code", sa.String(length=32), nullable=False),
        sa.Column("sector_name", sa.String(length=128), nullable=False),
        sa.Column("parent_sector_code", sa.String(length=32), nullable=True),
        sa.Column("sector_stock_count", sa.Integer(), nullable=False),
        sa.Column("sector_top_stock_count", sa.Integer(), nullable=False),
        sa.Column("top_density", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("median_return", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("momentum_score", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("small_sample_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["result_id"], ["factor_result.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_id", "level", "sector_code", name="uq_factor_row_result_level_sector"),
    )
    op.create_index("ix_factor_row_result_level_score", "factor_result_row", ["result_id", "level", "momentum_score"], unique=False)
    op.create_index("ix_factor_row_result_parent", "factor_result_row", ["result_id", "parent_sector_code"], unique=False)

    op.create_table(
        "factor_result_stock",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("stock_name", sa.String(length=64), nullable=False),
        sa.Column("l1_code", sa.String(length=32), nullable=True),
        sa.Column("l1_name", sa.String(length=128), nullable=True),
        sa.Column("l2_code", sa.String(length=32), nullable=True),
        sa.Column("l2_name", sa.String(length=128), nullable=True),
        sa.Column("l3_code", sa.String(length=32), nullable=True),
        sa.Column("l3_name", sa.String(length=128), nullable=True),
        sa.Column("stock_return", sa.Numeric(precision=14, scale=8), nullable=True),
        sa.Column("is_top", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("missing_reason", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["result_id"], ["factor_result.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("result_id", "ts_code", name="uq_factor_stock_result_ts_code"),
    )
    op.create_index("ix_factor_stock_result_l1_return", "factor_result_stock", ["result_id", "l1_code", "stock_return"], unique=False)
    op.create_index("ix_factor_stock_result_l2_return", "factor_result_stock", ["result_id", "l2_code", "stock_return"], unique=False)
    op.create_index("ix_factor_stock_result_l3_return", "factor_result_stock", ["result_id", "l3_code", "stock_return"], unique=False)
    op.create_index("ix_factor_stock_result_top", "factor_result_stock", ["result_id", "is_top"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_factor_stock_result_top", table_name="factor_result_stock")
    op.drop_index("ix_factor_stock_result_l3_return", table_name="factor_result_stock")
    op.drop_index("ix_factor_stock_result_l2_return", table_name="factor_result_stock")
    op.drop_index("ix_factor_stock_result_l1_return", table_name="factor_result_stock")
    op.drop_table("factor_result_stock")
    op.drop_index("ix_factor_row_result_parent", table_name="factor_result_row")
    op.drop_index("ix_factor_row_result_level_score", table_name="factor_result_row")
    op.drop_table("factor_result_row")
    op.drop_index("ix_factor_result_stale", table_name="factor_result")
    op.drop_index("ix_factor_result_created", table_name="factor_result")
    op.drop_index("ix_factor_result_class_basedate", table_name="factor_result")
    op.drop_index("ix_factor_result_basedate_created", table_name="factor_result")
    op.drop_table("factor_result")
    op.drop_index("ix_factor_config_owner_updated", table_name="factor_config")
    op.drop_table("factor_config")
    op.drop_index("ix_browse_history_user_key_visited", table_name="browse_history")
    op.drop_index("ix_browse_history_user_visited", table_name="browse_history")
    op.drop_table("browse_history")
