"""Stock detail API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.envelope import fail, ok
from app.core.errors import ValidationError
from app.services.stock_service import get_stock_detail, get_stock_kline

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/{ts_code}")
def stock_detail(
    ts_code: str,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    detail = get_stock_detail(db, ts_code)
    if detail is None:
        return JSONResponse(
            status_code=200,
            content=fail("NOT_FOUND_STOCK", f"stock {ts_code} not found", {"ts_code": ts_code}),
        )
    return ok(detail)


@router.get("/{ts_code}/kline")
def stock_kline(
    ts_code: str,
    start: str | None = Query(None),
    end: str | None = Query(None),
    adjust: str = Query("qfq"),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError as exc:
        raise ValidationError("VALIDATION_INVALID_DATE", "date must be YYYY-MM-DD") from exc
    return ok(get_stock_kline(db, ts_code, start=start_date, end=end_date, adjust=adjust))
