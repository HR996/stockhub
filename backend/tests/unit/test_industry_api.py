"""Unit tests for /api/industry/* endpoints — envelope shape + happy path.

Uses TestClient with FastAPI dependency_overrides + monkey-patched service functions,
so no real DB is required.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.deps import get_db
from app.main import create_app
from app.services.sw_query_service import (
    IndustryL1Node,
    IndustryL2Node,
    IndustryL3Node,
    IndustryTree,
    LastSyncInfo,
    NodeStockList,
    NodeStockRow,
    StockIndustry,
)


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: iter([None])
    return TestClient(app)


def test_tree_returns_envelope_with_nested_levels() -> None:
    tree = IndustryTree(
        src="SW2021",
        levels=[
            IndustryL1Node(
                index_code="801010.SI", industry_code="SW801010", industry_name="农林牧渔",
                children=[
                    IndustryL2Node(
                        index_code="801011.SI", industry_code="SW801011", industry_name="种植业",
                        children=[
                            IndustryL3Node(
                                index_code="801012.SI", industry_code="SW801012",
                                industry_name="粮食种植", stock_count=3,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
    with patch("app.api.industry.get_industry_tree", return_value=tree):
        resp = _client().get("/api/industry/tree")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["src"] == "SW2021"
    assert body["data"]["levels"][0]["industry_name"] == "农林牧渔"
    assert body["data"]["levels"][0]["children"][0]["children"][0]["stock_count"] == 3


def test_stock_returns_not_found_envelope_when_absent() -> None:
    with patch("app.api.industry.get_stock_industry", return_value=None):
        resp = _client().get("/api/industry/stock/999999.SH")
    body = resp.json()
    assert resp.status_code == 200
    assert body["success"] is False
    assert body["data"]["code"] == "NOT_FOUND_STOCK"


def test_stock_returns_industry_when_found() -> None:
    row = StockIndustry(
        ts_code="600123.SH",
        l1_index_code="801010.SI", l1_name="农林牧渔",
        l2_index_code="801011.SI", l2_name="种植业",
        l3_index_code="801012.SI", l3_name="粮食种植",
        in_date=date(2020, 1, 1), out_date=None,
    )
    with patch("app.api.industry.get_stock_industry", return_value=row):
        resp = _client().get("/api/industry/stock/600123.SH")
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["l1_name"] == "农林牧渔"
    assert body["data"]["in_date"] == "2020-01-01"


def test_last_sync_returns_status_or_null() -> None:
    info = LastSyncInfo(
        status="SUCCESS",
        started_at=datetime(2026, 7, 5, 2, 7, 0),
        finished_at=datetime(2026, 7, 5, 2, 9, 30),
        classify_expected=5000,
        classify_success=5000,
        orphan_count=0,
        error_message=None,
    )
    with patch("app.api.industry.get_last_sync_info", return_value=info):
        resp = _client().get("/api/industry/last-sync")
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "SUCCESS"
    assert body["data"]["classify_success"] == 5000


def test_node_stocks_level_lowercase_accepted() -> None:
    """lowercase l1 should be normalized to L1 before hitting the service."""
    node = NodeStockList(
        level="L1", index_code="801010.SI", industry_name="农林牧渔", total=0, stocks=[]
    )
    with patch("app.api.industry.get_stocks_under_node", return_value=node) as spy:
        resp = _client().get("/api/industry/node/l1/801010.SI/stocks")
    assert resp.json()["success"] is True
    assert spy.call_args.args[2] == "L1"


def test_node_stocks_returns_flat_list() -> None:
    node = NodeStockList(
        level="L3",
        index_code="801012.SI",
        industry_name="粮食种植",
        total=2,
        stocks=[
            NodeStockRow(
                ts_code="600123.SH", name="示例A",
                l1_index_code="801010.SI", l1_name="农林牧渔",
                l2_index_code="801011.SI", l2_name="种植业",
                l3_index_code="801012.SI", l3_name="粮食种植",
                in_date=date(2020, 1, 1),
            ),
            NodeStockRow(
                ts_code="600124.SH", name=None,
                l1_index_code="801010.SI", l1_name="农林牧渔",
                l2_index_code="801011.SI", l2_name="种植业",
                l3_index_code="801012.SI", l3_name="粮食种植",
                in_date=None,
            ),
        ],
    )
    with patch("app.api.industry.get_stocks_under_node", return_value=node):
        resp = _client().get("/api/industry/node/L3/801012.SI/stocks")
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["level"] == "L3"
    assert body["data"]["total"] == 2
    assert body["data"]["stocks"][0]["ts_code"] == "600123.SH"
    assert body["data"]["stocks"][0]["name"] == "示例A"
    assert body["data"]["stocks"][1]["name"] is None
    assert body["data"]["stocks"][0]["in_date"] == "2020-01-01"


def test_node_stocks_rejects_invalid_level() -> None:
    resp = _client().get("/api/industry/node/L9/801012.SI/stocks")
    body = resp.json()
    assert body["success"] is False
    assert body["data"]["code"] == "VALIDATION_INVALID_LEVEL"


def test_node_stocks_returns_not_found_when_absent() -> None:
    with patch("app.api.industry.get_stocks_under_node", return_value=None):
        resp = _client().get("/api/industry/node/L1/801999.SI/stocks")
    body = resp.json()
    assert body["success"] is False
    assert body["data"]["code"] == "NOT_FOUND_INDUSTRY_NODE"
