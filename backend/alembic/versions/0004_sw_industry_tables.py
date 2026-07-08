"""add sw industry classify and member tables

Revision ID: 0c8e21f4a900
Revises: 0b5d6b31a977
Create Date: 2026-07-08 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0c8e21f4a900"
down_revision: str | Sequence[str] | None = "0b5d6b31a977"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sw_industry_classify",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("index_code", sa.String(length=32), nullable=False),
        sa.Column("industry_code", sa.String(length=32), nullable=False),
        sa.Column("industry_name", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=4), nullable=False),
        sa.Column("parent_code", sa.String(length=32), nullable=True),
        sa.Column("is_pub", sa.Boolean(), nullable=True),
        sa.Column("src", sa.String(length=16), nullable=False, server_default="SW2021"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_code", name="uq_sw_industry_classify_index_code"),
        sa.UniqueConstraint("industry_code", name="uq_sw_industry_classify_industry_code"),
    )
    op.create_index(
        "ix_sw_industry_classify_level", "sw_industry_classify", ["level"], unique=False
    )
    op.create_index(
        "ix_sw_industry_classify_parent_code",
        "sw_industry_classify",
        ["parent_code"],
        unique=False,
    )

    op.create_table(
        "sw_industry_member",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=16), nullable=False),
        sa.Column("l1_index_code", sa.String(length=32), nullable=False),
        sa.Column("l1_name", sa.String(length=128), nullable=False),
        sa.Column("l2_index_code", sa.String(length=32), nullable=False),
        sa.Column("l2_name", sa.String(length=128), nullable=False),
        sa.Column("l3_index_code", sa.String(length=32), nullable=False),
        sa.Column("l3_name", sa.String(length=128), nullable=False),
        sa.Column("in_date", sa.Date(), nullable=True),
        sa.Column("out_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ts_code", name="uq_sw_industry_member_ts_code"),
    )
    op.create_index(
        "ix_sw_industry_member_l1", "sw_industry_member", ["l1_index_code"], unique=False
    )
    op.create_index(
        "ix_sw_industry_member_l2", "sw_industry_member", ["l2_index_code"], unique=False
    )
    op.create_index(
        "ix_sw_industry_member_l3", "sw_industry_member", ["l3_index_code"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_sw_industry_member_l3", table_name="sw_industry_member")
    op.drop_index("ix_sw_industry_member_l2", table_name="sw_industry_member")
    op.drop_index("ix_sw_industry_member_l1", table_name="sw_industry_member")
    op.drop_table("sw_industry_member")
    op.drop_index("ix_sw_industry_classify_parent_code", table_name="sw_industry_classify")
    op.drop_index("ix_sw_industry_classify_level", table_name="sw_industry_classify")
    op.drop_table("sw_industry_classify")
