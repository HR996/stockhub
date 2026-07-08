"""data_update_task Repository."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.data_update_task import DataUpdateTask


@dataclass(frozen=True)
class TaskLogRow:
    task_type: str
    status: str
    created_by: str
    task_key: str | None = None
    finished_at: datetime | None = None
    expected_count: int | None = None
    success_count: int | None = None
    missing_count: int | None = None
    error_count: int | None = None
    error_summary: dict[str, Any] | None = None


class TaskLogRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, row: TaskLogRow) -> int:
        model = DataUpdateTask(**row.__dict__)
        self._session.add(model)
        self._session.flush()
        return model.id

    def upsert_by_key(self, row: TaskLogRow) -> int:
        """Upsert on `(task_type, task_key)` — used when re-runs should overwrite prior attempts."""
        if row.task_key is None:
            return self.create(row)
        payload = row.__dict__
        stmt = insert(DataUpdateTask).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[DataUpdateTask.task_type, DataUpdateTask.task_key],
            index_where=DataUpdateTask.task_key.isnot(None),
            set_={
                "status": stmt.excluded.status,
                "finished_at": stmt.excluded.finished_at,
                "expected_count": stmt.excluded.expected_count,
                "success_count": stmt.excluded.success_count,
                "missing_count": stmt.excluded.missing_count,
                "error_count": stmt.excluded.error_count,
                "error_summary": stmt.excluded.error_summary,
                "created_by": stmt.excluded.created_by,
            },
        )
        result = self._session.execute(stmt.returning(DataUpdateTask.id))
        return int(result.scalar_one())

    def latest_by_type(self, task_type: str) -> DataUpdateTask | None:
        stmt = (
            select(DataUpdateTask)
            .where(DataUpdateTask.task_type == task_type)
            .order_by(DataUpdateTask.started_at.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def find_by_key(self, task_type: str, task_key: str) -> DataUpdateTask | None:
        stmt = select(DataUpdateTask).where(
            DataUpdateTask.task_type == task_type,
            DataUpdateTask.task_key == task_key,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def count(self) -> int:
        return int(self._session.execute(select(func.count(DataUpdateTask.id))).scalar_one())

    def list_recent(self, limit: int = 50) -> Sequence[DataUpdateTask]:
        stmt = select(DataUpdateTask).order_by(DataUpdateTask.started_at.desc()).limit(limit)
        return self._session.execute(stmt).scalars().all()

    ORDER_FIELDS: frozenset[str] = frozenset({
        "started_at", "finished_at", "task_type", "status",
    })

    def list_paged(
        self,
        page: int,
        page_size: int,
        order_by: str = "started_at",
        order: str = "desc",
    ) -> tuple[Sequence[DataUpdateTask], int]:
        """Return (rows, total) — total is unfiltered row count for pagination UI."""
        if order_by not in self.ORDER_FIELDS:
            raise ValueError(f"invalid order_by: {order_by}")
        if order not in ("asc", "desc"):
            raise ValueError(f"invalid order: {order}")

        column = getattr(DataUpdateTask, order_by)
        direction = column.desc() if order == "desc" else column.asc()

        total = self.count()
        stmt = (
            select(DataUpdateTask)
            .order_by(direction, DataUpdateTask.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = self._session.execute(stmt).scalars().all()
        return rows, total
