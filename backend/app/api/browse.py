"""Data browse API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.envelope import ok
from app.repositories.browse_history_repo import BrowseHistoryRepo
from app.services.browse_history_service import add_history, history_to_dict
from app.services.browse_service import list_tables, query_table

router = APIRouter(prefix="/api/browse", tags=["browse"])


@router.get("/tables")
def tables(user: str = Depends(get_current_user)) -> dict:
    _ = user
    return ok({"items": list_tables()})


@router.post("/tables/{table_key}/query")
def table_query(
    payload: dict[str, Any],
    table_key: str = Path(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    return ok(query_table(db, table_key, payload))


@router.get("/history")
def history_list(
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    rows = BrowseHistoryRepo(db).list_for_user(user)
    return ok({"items": [history_to_dict(r) for r in rows]})


@router.post("/history")
def history_add(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok(
        add_history(
            BrowseHistoryRepo(db),
            username=user,
            page_key=str(payload.get("page_key") or ""),
            page_title=str(payload.get("page_title") or ""),
            page_state=payload.get("page_state") or {},
        )
    )


@router.delete("/history/{history_id}")
def history_delete(
    history_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    deleted = BrowseHistoryRepo(db).delete_one(user, history_id)
    return ok({"deleted": deleted})


@router.delete("/history")
def history_clear(
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok({"deleted": BrowseHistoryRepo(db).delete_all(user)})
