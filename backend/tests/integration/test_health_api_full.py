"""P2-04 — Integration contract tests for new health endpoints (real PG)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.main import app
from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.stock_repo import StockBasicRepo, StockBasicRow
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow
from app.repositories.trade_cal_repo import TradeCalRepo, TradeCalRow

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_basic_universe(db) -> None:
    StockBasicRepo(db).upsert_many([
        StockBasicRow(
            ts_code="600000.SH", bs_code="sh.600000", name="浦发银行", market="SH",
            list_date=date(2000, 1, 1),
        ),
        StockBasicRow(
            ts_code="000001.SZ", bs_code="sz.000001", name="平安银行", market="SZ",
            list_date=date(2000, 1, 1),
        ),
    ])
    TradeCalRepo(db).upsert_many([
        TradeCalRow(cal_date=date(2024, 1, d), is_open=(d not in (1, 6, 7)))
        for d in range(1, 32)
    ])
    db.commit()


def test_calendar_endpoint_reflects_kline_coverage(client, db) -> None:
    _seed_basic_universe(db)
    # 1/2 fully covered; 1/3 partial (only 1 of 2); 1/4 no rows
    KLineRepo(db).upsert_many([
        KLineRow(ts_code="600000.SH", trade_date=date(2024, 1, 2),
                 trade_status=1, close_raw=Decimal("10.00")),
        KLineRow(ts_code="000001.SZ", trade_date=date(2024, 1, 2),
                 trade_status=1, close_raw=Decimal("12.00")),
        KLineRow(ts_code="600000.SH", trade_date=date(2024, 1, 3),
                 trade_status=1, close_raw=Decimal("10.10")),
    ])
    db.commit()

    r = client.get("/api/health/kline/calendar", params={"year": 2024, "month": 1})
    body = r.json()
    assert body["success"] is True
    by_date = {d["date"]: d for d in body["data"]["days"]}

    assert by_date["2024-01-02"]["status"] == "green"
    assert by_date["2024-01-03"]["status"] == "yellow"
    assert by_date["2024-01-04"]["status"] == "red"
    assert by_date["2024-01-06"]["status"] == "gray"  # Saturday
    assert by_date["2024-01-01"]["status"] == "gray"  # NYE holiday (is_open=False)


def test_day_endpoint_reflects_kline_gaps(client, db) -> None:
    _seed_basic_universe(db)
    # Only 600000 fetched; 000001 missing on Jan 2
    KLineRepo(db).upsert_many([
        KLineRow(ts_code="600000.SH", trade_date=date(2024, 1, 2),
                 trade_status=1, close_raw=Decimal("10.00")),
    ])
    db.commit()

    r = client.get("/api/health/kline/day/2024-01-02")
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["expected_count"] == 2
    assert data["success_count"] == 1
    assert data["missing_count"] == 1
    assert data["missing_ts_codes"] == ["000001.SZ"]


def test_day_endpoint_non_trading_day_maps_to_not_found_envelope(client, db) -> None:
    _seed_basic_universe(db)
    r = client.get("/api/health/kline/day/2024-01-06")  # Saturday
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "NOT_FOUND_TRADING_DAY"


def test_tasks_endpoint_pagination(client, db) -> None:
    task_repo = TaskLogRepo(db)
    for i in range(1, 6):
        task_repo.create(TaskLogRow(
            task_type="SYNC_KLINE",
            status="SUCCESS",
            created_by="scheduler",
            finished_at=datetime(2026, 7, 7, i, 0, tzinfo=UTC),
        ))
    db.commit()

    r = client.get("/api/health/tasks", params={"page": 1, "page_size": 2, "order": "desc"})
    body = r.json()
    d = body["data"]
    assert d["total"] == 5
    assert d["page"] == 1 and d["page_size"] == 2
    assert len(d["items"]) == 2

    r2 = client.get("/api/health/tasks", params={"page": 3, "page_size": 2})
    d2 = r2.json()["data"]
    assert len(d2["items"]) == 1  # 5 rows / page_size 2 → last page has 1


def test_tasks_endpoint_rejects_bad_page_size(client) -> None:
    r = client.get("/api/health/tasks", params={"page_size": 999})
    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "VALIDATION_PAGE_SIZE_TOO_LARGE"
