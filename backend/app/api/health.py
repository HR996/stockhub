"""Health API — P1-01 / P1-07 / P2-04.

Endpoints:
- GET /api/health                           liveness probe
- GET /api/health/summary                   4 core tables + latest task snapshot
- GET /api/health/kline/calendar?year&month K 线月历状态（P2-01 service）
- GET /api/health/kline/day/{date}          单日健康详情（P2-02 service）
- GET /api/health/tasks                     任务日志分页列表
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.envelope import fail, ok
from app.core.errors import NotFoundError, ValidationError
from app.repositories.kline_repo import KLineRepo
from app.repositories.stock_repo import StockBasicRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.repositories.trade_cal_repo import TradeCalRepo
from app.services.health_calendar_service import CalendarMonth, DayStatus, get_calendar
from app.services.health_day_service import DayDetail, get_day_detail
from app.services.health_service import get_summary, summary_to_dict

router = APIRouter(prefix="/api/health", tags=["health"])

PAGE_SIZE_MAX = 200
PAGE_SIZE_DEFAULT = 50


@router.get("")
def health() -> dict:
    """Liveness probe — proves the service is up."""
    return ok(
        {
            "app": settings.app_name,
            "version": settings.app_version,
            "server_time": datetime.now(UTC).isoformat(),
        }
    )


@router.get("/summary")
def health_summary(
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    """Per-table row count + last-updated timestamp for the 4 core tables + latest task."""
    _ = user  # stub for future auth (P2-05)
    return ok(summary_to_dict(get_summary(db)))


@router.get("/kline/calendar")
def kline_calendar(
    year: int = Query(..., ge=1990, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    """K-line completeness calendar for the given month (US-3.2)."""
    _ = user
    result = get_calendar(
        year, month,
        trade_cal_repo=TradeCalRepo(db),
        stock_repo=StockBasicRepo(db),
        kline_repo=KLineRepo(db),
    )
    return ok(_calendar_to_dict(result))


@router.get("/kline/day/{day}")
def kline_day_detail(
    day: str,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    """Single-day K-line health detail (US-3.3)."""
    _ = user
    try:
        d = date.fromisoformat(day)
    except ValueError as exc:
        raise ValidationError(
            "VALIDATION_INVALID_DATE",
            f"invalid date format: {day} (expect YYYY-MM-DD)",
            detail={"field": "day", "reason": str(exc)},
        ) from exc

    detail = get_day_detail(
        d,
        trade_cal_repo=TradeCalRepo(db),
        stock_repo=StockBasicRepo(db),
        kline_repo=KLineRepo(db),
        task_repo=TaskLogRepo(db),
    )
    return ok(_day_detail_to_dict(detail))


@router.get("/tasks")
def tasks_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1),
    order_by: str = Query("started_at"),
    order: str = Query("desc"),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    """Paginated data_update_task list (US-3.4)."""
    _ = user
    if page_size > PAGE_SIZE_MAX:
        raise ValidationError(
            "VALIDATION_PAGE_SIZE_TOO_LARGE",
            f"page_size {page_size} exceeds max {PAGE_SIZE_MAX}",
            detail={"field": "page_size", "max": PAGE_SIZE_MAX},
        )
    if order_by not in TaskLogRepo.ORDER_FIELDS:
        raise ValidationError(
            "VALIDATION_INVALID_ORDER_FIELD",
            f"unknown order_by: {order_by}",
            detail={"field": "order_by", "allowed": sorted(TaskLogRepo.ORDER_FIELDS)},
        )
    if order not in ("asc", "desc"):
        raise ValidationError(
            "VALIDATION_INVALID_ORDER",
            f"unknown order direction: {order}",
            detail={"field": "order", "allowed": ["asc", "desc"]},
        )

    rows, total = TaskLogRepo(db).list_paged(
        page=page, page_size=page_size, order_by=order_by, order=order
    )
    return ok({
        "items": [_task_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ---------- serializers ----------

def _calendar_to_dict(m: CalendarMonth) -> dict:
    return {
        "year": m.year,
        "month": m.month,
        "days": [_day_status_to_dict(d) for d in m.days],
    }


def _day_status_to_dict(d: DayStatus) -> dict:
    return {
        "date": d.cal_date.isoformat(),
        "is_open": d.is_open,
        "status": d.status,
        "expected": d.expected,
        "actual": d.actual,
        "has_anomaly": d.has_anomaly,
    }


def _day_detail_to_dict(d: DayDetail) -> dict:
    return {
        "date": d.day.isoformat(),
        "expected_count": d.expected_count,
        "success_count": d.success_count,
        "missing_count": d.missing_count,
        "error_count": d.error_count,
        "missing_ts_codes": list(d.missing_ts_codes),
        "error_ts_codes": list(d.error_ts_codes),
        "latest_task": {
            "status": d.latest_task_status,
            "finished_at": d.latest_task_finished_at.isoformat()
                if d.latest_task_finished_at else None,
            "error_summary": d.latest_task_error_summary,
        } if d.latest_task_status is not None else None,
    }


def _task_to_dict(row) -> dict:
    return {
        "id": row.id,
        "task_type": row.task_type,
        "task_key": row.task_key,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "expected_count": row.expected_count,
        "success_count": row.success_count,
        "missing_count": row.missing_count,
        "error_count": row.error_count,
        "error_summary": row.error_summary,
        "created_by": row.created_by,
    }


# Re-export for handlers/tests
__all__ = ["NotFoundError", "ValidationError", "fail", "router"]
