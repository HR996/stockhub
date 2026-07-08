"""P1-04 (redo) — Unit tests for baostock_profit helpers using fake ResultSet."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class _FakeRs:
    def __init__(self, rows: list[list[str]], fields: list[str], error_code: str = "0",
                 error_msg: str = "") -> None:
        self._rows = list(rows)
        self.fields = fields
        self.error_code = error_code
        self.error_msg = error_msg

    def next(self) -> bool:
        return len(self._rows) > 0

    def get_row_data(self) -> list[str]:
        return self._rows.pop(0)


_PROFIT_FIELDS = [
    "code", "pubDate", "statDate",
    "roeAvg", "npMargin", "gpMargin",
    "netProfit", "epsTTM", "MBRevenue",
    "totalShare", "liqaShare",
]


def _profit_rs(total_share: str, liqa_share: str, pub: str = "2025-04-30",
               stat: str = "2025-03-31") -> _FakeRs:
    return _FakeRs(
        rows=[[
            "sh.600000", pub, stat, "0.02", "0.3", "",
            "1e10", "1.5", "", total_share, liqa_share,
        ]],
        fields=_PROFIT_FIELDS,
    )


def test_fetch_profit_data_happy_path() -> None:
    from app.adapters.baostock_profit import fetch_profit_data

    rs = _profit_rs("29352178996.00", "29352178996.00")
    with patch("app.adapters.baostock_profit.bs.query_profit_data", return_value=rs):
        row = fetch_profit_data("sh.600000", year=2025, quarter=1)

    assert row is not None
    assert row.bs_code == "sh.600000"
    assert row.pub_date == date(2025, 4, 30)
    assert row.stat_date == date(2025, 3, 31)
    assert row.total_share == Decimal("29352178996.00")
    assert row.liqa_share == Decimal("29352178996.00")


def test_fetch_profit_data_returns_none_when_empty() -> None:
    from app.adapters.baostock_profit import fetch_profit_data

    rs = _FakeRs(rows=[], fields=_PROFIT_FIELDS)
    with patch("app.adapters.baostock_profit.bs.query_profit_data", return_value=rs):
        row = fetch_profit_data("bj.999999", year=2025, quarter=1)

    assert row is None


def test_fetch_profit_data_raises_on_baostock_error() -> None:
    from app.adapters.baostock_profit import fetch_profit_data
    from app.core.errors import AdapterConnectionError

    rs = SimpleNamespace(error_code="10001001", error_msg="internal error")
    with (
        patch("app.adapters.baostock_profit.bs.query_profit_data", return_value=rs),
        pytest.raises(AdapterConnectionError, match="query_profit_data"),
    ):
        fetch_profit_data("sh.600000", year=2025, quarter=1)


def test_fetch_profit_data_treats_empty_share_as_none() -> None:
    from app.adapters.baostock_profit import fetch_profit_data

    rs = _profit_rs("", "")
    with patch("app.adapters.baostock_profit.bs.query_profit_data", return_value=rs):
        row = fetch_profit_data("sh.600000", year=2025, quarter=1)

    assert row is not None
    assert row.total_share is None
    assert row.liqa_share is None
