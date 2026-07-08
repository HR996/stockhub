"""data_update_task — 数据更新任务日志（对齐 docs/05_DATA_MODEL.md §6.1）."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, mapped_col_created_at


class DataUpdateTask(Base):
    __tablename__ = "data_update_task"
    __table_args__ = (
        Index("ix_data_update_task_type_started", "task_type", "started_at"),
        Index("ix_data_update_task_status_started", "status", "started_at"),
        Index(
            "uq_data_update_task_type_key",
            "task_type",
            "task_key",
            unique=True,
            postgresql_where="task_key IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    task_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_col_created_at()
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missing_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
