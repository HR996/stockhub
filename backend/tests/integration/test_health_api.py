"""P1-07 — Integration contract test for /api/health/summary."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.main import app
from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.market_cap_repo import MarketCapRepo, MarketCapUpsertRow
from app.repositories.stock_repo import StockBasicRepo, StockBasicRow
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow
from app.repositories.trade_cal_repo import TradeCalRepo, TradeCalRow

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(db):
    """Wire the FastAPI app to reuse the same test DB session.

    The `get_db` dependency yields a transactional session by default; here we
    override it to hand back the pytest-managed one so writes and the endpoint
    call see the same transaction.
    """
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_summary_empty_state(client, db) -> None:
    resp = client.get("/api/health/summary")
    assert resp.status_code == 200
    body = resp.json()

    assert body["success"] is True
    assert body["message"] == ""

    data = body["data"]
    for table in ("stock_basic", "trade_calendar", "k_line_daily",
                  "latest_market_cap", "latest_task"):
        assert table in data
        assert data[table]["count"] == 0
        assert data[table]["last_updated"] is None


def test_health_summary_reports_counts_and_timestamps(client, db) -> None:
    # Populate each of the four core tables + one task log entry.
    StockBasicRepo(db).upsert_many([
        StockBasicRow(ts_code="600000.SH", bs_code="sh.600000",
                      name="浦发银行", market="SH"),
        StockBasicRow(ts_code="000001.SZ", bs_code="sz.000001",
                      name="平安银行", market="SZ"),
    ])
    TradeCalRepo(db).upsert_many([
        TradeCalRow(cal_date=date(2024, 1, d), is_open=(d not in (6, 7)))
        for d in range(1, 8)
    ])
    KLineRepo(db).upsert_many([
        KLineRow(ts_code="600000.SH", trade_date=date(2024, 1, 2),
                 close_qfq=Decimal("10.00")),
    ])
    MarketCapRepo(db).upsert_many([
        MarketCapUpsertRow(ts_code="600000.SH", market_cap_source="baostock_synth",
                           total_market_cap=Decimal("1000")),
    ])
    TaskLogRepo(db).create(TaskLogRow(
        task_type="SYNC_KLINE", status="SUCCESS", created_by="scheduler",
    ))
    db.commit()

    resp = client.get("/api/health/summary")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["stock_basic"]["count"] == 2
    assert data["stock_basic"]["last_updated"] is not None
    assert data["trade_calendar"]["count"] == 7
    assert data["k_line_daily"]["count"] == 1
    assert data["latest_market_cap"]["count"] == 1
    assert data["latest_task"]["count"] == 1


def test_health_summary_x_user_header_accepted(client) -> None:
    """Stub auth: header is accepted, endpoint still 200. Real validation is P2-05."""
    resp = client.get("/api/health/summary", headers={"X-User": "alice"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
