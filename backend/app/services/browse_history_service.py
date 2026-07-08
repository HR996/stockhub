"""Browse history service."""

from __future__ import annotations

from typing import Any

from app.repositories.browse_history_repo import BrowseHistoryCreate, BrowseHistoryRepo


def add_history(
    repo: BrowseHistoryRepo,
    *,
    username: str,
    page_key: str,
    page_title: str,
    page_state: dict[str, Any],
) -> dict[str, Any]:
    row = repo.add(
        BrowseHistoryCreate(
            username=username,
            page_key=page_key,
            page_title=page_title,
            page_state=page_state,
        )
    )
    repo.trim(username, keep=100)
    return history_to_dict(row)


def history_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "username": row.username,
        "page_key": row.page_key,
        "page_title": row.page_title,
        "page_state": row.page_state,
        "visited_at": row.visited_at.isoformat() if row.visited_at else None,
    }
