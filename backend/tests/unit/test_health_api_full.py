"""P2-04 — Contract tests for health endpoints (no DB, dependency overrides)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.main import app

# ---------- fake dependency + fake repos ----------

class _FakeDb:
    """Sentinel session — repos are patched, so this object is never read from."""


def _override_db():
    yield _FakeDb()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------- kline_calendar tests ----------

def test_calendar_success(client) -> None:
    from app.services.health_calendar_service import (
        STATUS_GRAY,
        STATUS_GREEN,
        CalendarMonth,
        DayStatus,
    )

    fake = CalendarMonth(
        year=2024, month=1,
        days=[
            DayStatus(date(2024, 1, 1), False, STATUS_GRAY, 0, 0, False),
            DayStatus(date(2024, 1, 2), True, STATUS_GREEN, 100, 100, False),
        ],
    )
    with patch("app.api.health.get_calendar", return_value=fake):
        r = client.get("/api/health/kline/calendar", params={"year": 2024, "month": 1})

    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["year"] == 2024 and body["data"]["month"] == 1
    days = body["data"]["days"]
    assert len(days) == 2
    assert days[0]["status"] == "gray"
    assert days[1]["status"] == "green"
    assert days[1]["expected"] == 100 and days[1]["actual"] == 100


def test_calendar_rejects_invalid_month(client) -> None:
    r = client.get("/api/health/kline/calendar", params={"year": 2024, "month": 13})
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"].startswith("VALIDATION_")


def test_calendar_missing_query_param(client) -> None:
    r = client.get("/api/health/kline/calendar", params={"year": 2024})
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "VALIDATION_INVALID_PARAMETER"


# ---------- kline_day tests ----------

def test_day_detail_success(client) -> None:
    from app.services.health_day_service import DayDetail

    fake = DayDetail(
        day=date(2024, 1, 2),
        expected_count=100, success_count=95, missing_count=3, error_count=2,
        missing_ts_codes=["A.SH", "B.SH", "C.SH"],
        error_ts_codes=["X.SH", "Y.SH"],
        latest_task_status="SUCCESS",
        latest_task_finished_at=datetime(2026, 7, 7, 3, 0, tzinfo=UTC),
        latest_task_error_summary={"errors": []},
    )
    with patch("app.api.health.get_day_detail", return_value=fake):
        r = client.get("/api/health/kline/day/2024-01-02")

    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["date"] == "2024-01-02"
    assert data["expected_count"] == 100
    assert data["success_count"] == 95
    assert data["missing_ts_codes"] == ["A.SH", "B.SH", "C.SH"]
    assert data["latest_task"]["status"] == "SUCCESS"


def test_day_detail_non_trading_day_returns_not_found_envelope(client) -> None:
    from app.core.errors import NotFoundError

    with patch("app.api.health.get_day_detail", side_effect=NotFoundError("not a trading day")):
        r = client.get("/api/health/kline/day/2024-01-06")

    assert r.status_code == 200  # envelope, not 404
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "NOT_FOUND_TRADING_DAY"


def test_day_detail_rejects_malformed_date(client) -> None:
    r = client.get("/api/health/kline/day/not-a-date")
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "VALIDATION_INVALID_DATE"


# ---------- tasks pagination tests ----------

@dataclass
class _FakeTaskRow:
    id: int = 1
    task_type: str = "SYNC_KLINE"
    task_key: str | None = None
    status: str = "SUCCESS"
    started_at: datetime | None = field(default_factory=lambda: datetime(2026, 7, 7, tzinfo=UTC))
    finished_at: datetime | None = None
    expected_count: int | None = None
    success_count: int | None = None
    missing_count: int | None = None
    error_count: int | None = None
    error_summary: dict[str, Any] | None = None
    created_by: str = "scheduler"


def test_tasks_pagination_success(client) -> None:
    rows = [_FakeTaskRow(id=i, status="SUCCESS") for i in range(1, 4)]

    with patch("app.api.health.TaskLogRepo") as MockRepo:
        MockRepo.ORDER_FIELDS = {"started_at", "finished_at", "task_type", "status"}
        MockRepo.return_value.list_paged.return_value = (rows, 42)

        r = client.get("/api/health/tasks", params={"page": 2, "page_size": 3})

    body = r.json()
    assert body["success"] is True
    d = body["data"]
    assert d["total"] == 42 and d["page"] == 2 and d["page_size"] == 3
    assert len(d["items"]) == 3
    assert d["items"][0]["id"] == 1
    assert d["items"][0]["created_by"] == "scheduler"


def test_tasks_page_size_over_max_rejected(client) -> None:
    r = client.get("/api/health/tasks", params={"page_size": 500})
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "VALIDATION_PAGE_SIZE_TOO_LARGE"
    assert body["data"]["detail"]["max"] == 200


def test_tasks_invalid_order_by_rejected(client) -> None:
    r = client.get("/api/health/tasks", params={"order_by": "created_by"})
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "VALIDATION_INVALID_ORDER_FIELD"
    # detail exposes the allowed whitelist so the frontend can render a dropdown
    assert "started_at" in body["data"]["detail"]["allowed"]


def test_tasks_invalid_order_direction_rejected(client) -> None:
    r = client.get("/api/health/tasks", params={"order": "sideways"})
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "VALIDATION_INVALID_ORDER"


def test_tasks_defaults_used_when_no_params(client) -> None:
    with patch("app.api.health.TaskLogRepo") as MockRepo:
        MockRepo.ORDER_FIELDS = {"started_at", "finished_at", "task_type", "status"}
        MockRepo.return_value.list_paged.return_value = ([], 0)
        r = client.get("/api/health/tasks")
        MockRepo.return_value.list_paged.assert_called_once()
        kwargs = MockRepo.return_value.list_paged.call_args.kwargs
        assert kwargs["page"] == 1
        assert kwargs["page_size"] == 50
        assert kwargs["order_by"] == "started_at"
        assert kwargs["order"] == "desc"

    body = r.json()
    assert body["success"] is True
    assert body["data"]["page"] == 1 and body["data"]["page_size"] == 50
