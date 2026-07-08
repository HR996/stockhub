"""P1-03 — Unit tests for baostock adapter helpers (no network)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from app.adapters.baostock_adapter import (
    _bs_to_ts_code,
    _market_from_bs,
    _parse_date,
    _parse_decimal,
    _rs_to_df,
)
from app.core.errors import AdapterConnectionError, AdapterDataError, AdapterQuotaExceededError


class _FakeRs:
    """Minimal stand-in for baostock ResultSet."""

    def __init__(self, rows: list[list[str]], fields: list[str], error_code: str = "0",
                 error_msg: str = "success") -> None:
        self._rows = list(rows)
        self.fields = fields
        self.error_code = error_code
        self.error_msg = error_msg

    def next(self) -> bool:
        return len(self._rows) > 0

    def get_row_data(self) -> list[str]:
        return self._rows.pop(0)


def test_bs_to_ts_code_maps_all_markets() -> None:
    assert _bs_to_ts_code("sh.600000") == "600000.SH"
    assert _bs_to_ts_code("sz.000001") == "000001.SZ"
    assert _bs_to_ts_code("bj.430047") == "430047.BJ"


def test_market_from_bs() -> None:
    assert _market_from_bs("sh.600000") == "SH"
    assert _market_from_bs("bj.430047") == "BJ"


def test_parse_date_handles_empty_and_iso() -> None:
    assert _parse_date("") is None
    assert _parse_date(None) is None
    assert _parse_date("2026-07-07") == date(2026, 7, 7)


def test_parse_decimal_treats_empty_as_none() -> None:
    """Suspended-day rows return empty strings from baostock — must become None, not 0."""
    assert _parse_decimal("") is None
    assert _parse_decimal(None) is None
    assert _parse_decimal("10.5") == Decimal("10.5")
    # Malformed input becomes None rather than raising (adapter is lenient upstream).
    assert _parse_decimal("not-a-number") is None


def test_rs_to_df_success() -> None:
    rs = _FakeRs(
        rows=[["600000", "浦发银行"], ["000001", "平安银行"]],
        fields=["code", "code_name"],
    )
    df = _rs_to_df(rs, "query_stock_basic")
    assert list(df.columns) == ["code", "code_name"]
    assert len(df) == 2
    assert df.iloc[0]["code"] == "600000"


def test_rs_to_df_raises_on_error_code() -> None:
    rs = SimpleNamespace(error_code="999999", error_msg="data error")
    with pytest.raises(AdapterDataError, match="query_stock_basic"):
        _rs_to_df(rs, "query_stock_basic")


def test_rs_to_df_maps_not_logged_in_to_connection_error() -> None:
    rs = SimpleNamespace(error_code="10001001", error_msg="用户未登录")
    with pytest.raises(AdapterConnectionError, match="connection lost"):
        _rs_to_df(rs, "query_history_k_data_plus")


def test_rs_to_df_empty_result() -> None:
    rs = _FakeRs(rows=[], fields=["code"])
    df = _rs_to_df(rs, "query_stock_basic")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_rs_to_df_raises_quota_exceeded_on_10001007() -> None:
    """baostock 5万次/日预算触顶 → AdapterQuotaExceededError（非 AdapterDataError）。"""
    rs = SimpleNamespace(error_code="10001007", error_msg="用户请求次数超过限制")
    with pytest.raises(AdapterQuotaExceededError, match="quota exceeded"):
        _rs_to_df(rs, "query_history_k_data_plus")


def test_baostock_session_maps_10001007_to_quota_error() -> None:
    """login 触顶时也走 AdapterQuotaExceededError 分支。"""
    from unittest.mock import patch

    from app.adapters.baostock_adapter import baostock_session

    fake_login_rs = SimpleNamespace(error_code="10001007", error_msg="用户请求次数超过限制")
    with (
        patch("app.adapters.baostock_adapter.bs.login", return_value=fake_login_rs),
        pytest.raises(AdapterQuotaExceededError),
        baostock_session(),
    ):
        pass
