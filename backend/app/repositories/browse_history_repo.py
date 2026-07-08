"""Repository for browse history rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.browse_history import BrowseHistory


@dataclass(frozen=True)
class BrowseHistoryCreate:
    username: str
    page_key: str
    page_title: str
    page_state: dict[str, Any]


class BrowseHistoryRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, row: BrowseHistoryCreate) -> BrowseHistory:
        obj = BrowseHistory(
            username=row.username,
            page_key=row.page_key,
            page_title=row.page_title,
            page_state=row.page_state,
        )
        self._session.add(obj)
        self._session.flush()
        return obj

    def list_for_user(self, username: str, limit: int = 100) -> list[BrowseHistory]:
        stmt = (
            select(BrowseHistory)
            .where(BrowseHistory.username == username)
            .order_by(BrowseHistory.visited_at.desc(), BrowseHistory.id.desc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    def delete_one(self, username: str, history_id: int) -> bool:
        stmt = delete(BrowseHistory).where(
            BrowseHistory.username == username, BrowseHistory.id == history_id
        )
        result = self._session.execute(stmt)
        return bool(result.rowcount)

    def delete_all(self, username: str) -> int:
        result = self._session.execute(
            delete(BrowseHistory).where(BrowseHistory.username == username)
        )
        return int(result.rowcount or 0)

    def trim(self, username: str, keep: int = 100) -> int:
        ranked = (
            select(BrowseHistory.id)
            .where(BrowseHistory.username == username)
            .order_by(BrowseHistory.visited_at.desc(), BrowseHistory.id.desc())
            .offset(keep)
            .subquery()
        )
        result = self._session.execute(
            delete(BrowseHistory).where(BrowseHistory.id.in_(select(ranked.c.id)))
        )
        return int(result.rowcount or 0)

    def latest_visit(self, username: str, page_key: str) -> datetime | None:
        stmt = select(func.max(BrowseHistory.visited_at)).where(
            BrowseHistory.username == username,
            BrowseHistory.page_key == page_key,
        )
        return self._session.execute(stmt).scalar_one()
