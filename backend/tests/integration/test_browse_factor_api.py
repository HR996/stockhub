"""Phase 3/5 integration smoke tests for browse/history/factor APIs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.main import app
from app.repositories.adj_factor_repo import AdjFactorRepo, AdjFactorUpsertRow
from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.market_cap_repo import MarketCapRepo, MarketCapUpsertRow
from app.repositories.stock_repo import StockBasicRepo, StockBasicRow
from app.repositories.sw_repo import SWClassifyRecord, SWClassifyRepo, SWMemberRecord, SWMemberRepo
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


def test_browse_tables_query_and_history(client, db) -> None:
    StockBasicRepo(db).upsert_many([
        StockBasicRow("600000.SH", "sh.600000", "浦发银行", "SH", date(2024, 1, 1)),
        StockBasicRow("000001.SZ", "sz.000001", "平安银行", "SZ", date(2024, 1, 1)),
    ])
    db.commit()

    tables = client.get("/api/browse/tables").json()
    assert tables["success"] is True
    assert any(t["key"] == "stock_basic" for t in tables["data"]["items"])

    resp = client.post(
        "/api/browse/tables/stock_basic/query",
        json={
            "page": 1,
            "page_size": 20,
            "fields": ["ts_code", "name"],
            "order_by": "ts_code",
            "filters": [{"field": "name", "op": "contains", "value": "银行"}],
        },
    ).json()
    assert resp["success"] is True
    assert resp["data"]["total"] == 2

    saved = client.post(
        "/api/browse/history",
        json={
            "page_key": "browse:stock_basic",
            "page_title": "股票基础信息",
            "page_state": {"page": 1},
        },
        headers={"X-User": "alice"},
    ).json()
    assert saved["success"] is True
    history = client.get("/api/browse/history", headers={"X-User": "alice"}).json()
    assert len(history["data"]["items"]) == 1


def test_factor_calculate_drilldown_and_sector_stocks(client, db) -> None:
    _seed_factor_universe(db)
    resp = client.post(
        "/api/factor/results",
        json={
            "basedate": "2024-01-31",
            "window": 2,
            "top_ratio": 0.5,
            "classification": "SW",
            "level": "L2",
            "return_method": "simple",
            "score_method": "median_return_score",
        },
        headers={"X-User": "alice"},
    ).json()
    assert resp["success"] is True
    result_id = resp["data"]["result"]["id"]
    assert resp["data"]["level"] == "L2"
    assert len(resp["data"]["rows"]) == 2

    children = client.get(
        f"/api/factor/results/{result_id}/children",
        params={"parent_level": "L1", "parent_sector_code": "801000.SI"},
    ).json()
    assert children["success"] is True
    assert children["data"]["level"] == "L2"
    assert len(children["data"]["rows"]) == 2

    stocks = client.get(
        f"/api/factor/results/{result_id}/sectors/L2/802000.SI/stocks"
    ).json()
    assert stocks["success"] is True
    assert stocks["data"]["stocks"][0]["stock_return"] is not None


def _seed_factor_universe(db) -> None:
    TradeCalRepo(db).upsert_many([
        TradeCalRow(date(2024, 1, d), True)
        for d in range(1, 32)
    ])
    stock_rows: list[StockBasicRow] = []
    cap_rows: list[MarketCapUpsertRow] = []
    k_rows: list[KLineRow] = []
    factor_rows: list[AdjFactorUpsertRow] = []
    member_rows: list[SWMemberRecord] = []
    returns = [Decimal("1.30"), Decimal("1.20"), Decimal("1.10"), Decimal("1.05"), Decimal("0.95"), Decimal("0.90")]
    for i, ratio in enumerate(returns, 1):
        code = f"60000{i}.SH"
        stock_rows.append(StockBasicRow(code, f"sh.60000{i}", f"样本{i}", "SH", date(2024, 1, 1)))
        cap_rows.append(MarketCapUpsertRow(code, "baostock_synth", total_market_cap=Decimal("20000000000")))
        k_rows.extend([
            KLineRow(ts_code=code, trade_date=date(2024, 1, 29), close_raw=Decimal("10.00"), trade_status=1),
            KLineRow(ts_code=code, trade_date=date(2024, 1, 31), close_raw=Decimal("10.00") * ratio, trade_status=1),
        ])
        factor_rows.extend([
            AdjFactorUpsertRow(code, date(2024, 1, 29), Decimal("1")),
            AdjFactorUpsertRow(code, date(2024, 1, 31), Decimal("1")),
        ])
        l2_code = "802000.SI" if i <= 3 else "802100.SI"
        l2_name = "二级A" if i <= 3 else "二级B"
        l3_code = "803000.SI" if i <= 3 else "803100.SI"
        l3_name = "三级A" if i <= 3 else "三级B"
        member_rows.append(
            SWMemberRecord(
                ts_code=code,
                l1_index_code="801000.SI",
                l1_name="一级",
                l2_index_code=l2_code,
                l2_name=l2_name,
                l3_index_code=l3_code,
                l3_name=l3_name,
                in_date=date(2024, 1, 1),
                out_date=None,
            )
        )
    StockBasicRepo(db).upsert_many(stock_rows)
    MarketCapRepo(db).upsert_many(cap_rows)
    KLineRepo(db).upsert_many(k_rows)
    AdjFactorRepo(db).upsert_many(factor_rows)
    SWClassifyRepo(db).replace_all([
        SWClassifyRecord("801000.SI", "801000", "一级", "L1", None, True, "SW2021"),
        SWClassifyRecord("802000.SI", "802000", "二级A", "L2", "801000", True, "SW2021"),
        SWClassifyRecord("802100.SI", "802100", "二级B", "L2", "801000", True, "SW2021"),
        SWClassifyRecord("803000.SI", "803000", "三级A", "L3", "802000", True, "SW2021"),
        SWClassifyRecord("803100.SI", "803100", "三级B", "L3", "802100", True, "SW2021"),
    ])
    SWMemberRepo(db).replace_all(member_rows)
    db.commit()
