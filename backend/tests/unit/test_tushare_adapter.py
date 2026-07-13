"""Unit tests for the Tushare adapter — no network calls."""

from __future__ import annotations

import dataclasses
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.adapters.tushare_adapter import (
    _map_tushare_error,
    _parse_bool,
    _parse_decimal,
    _parse_tushare_date,
    _rows_from_member_df,
    fetch_adj_factor_by_trade_date,
    fetch_daily_basic_by_trade_date,
    fetch_daily_by_trade_date,
    fetch_sw_classify,
    fetch_sw_members,
    fetch_trade_cal,
    tushare_session,
)
from app.adapters.tushare_types import SWClassifyRow
from app.core.errors import (
    AdapterAuthError,
    AdapterDataError,
    AdapterQuotaExceededError,
)


def test_parse_bool_variants() -> None:
    assert _parse_bool("Y") is True
    assert _parse_bool("N") is False
    assert _parse_bool("1") is True
    assert _parse_bool("0") is False
    assert _parse_bool("") is None
    assert _parse_bool(None) is None


def test_parse_tushare_date() -> None:
    assert _parse_tushare_date("20240701") == date(2024, 7, 1)
    assert _parse_tushare_date("2024-07-01") == date(2024, 7, 1)
    assert _parse_tushare_date(None) is None
    assert _parse_tushare_date("") is None
    assert _parse_tushare_date("nan") is None
    assert _parse_tushare_date("garbage") is None


def test_parse_decimal() -> None:
    assert _parse_decimal("12.34")
    assert _parse_decimal("") is None
    assert _parse_decimal("nan") is None
    assert _parse_decimal("broken") is None


def test_map_tushare_error_categories() -> None:
    assert isinstance(_map_tushare_error(Exception("token 无效"), "x"), AdapterAuthError)
    assert isinstance(_map_tushare_error(Exception("接口权限未开通"), "x"), AdapterAuthError)
    assert isinstance(_map_tushare_error(Exception("您的IP数量超限，最大数量为5个！"), "x"), AdapterAuthError)
    assert isinstance(_map_tushare_error(Exception("积分不足"), "x"), AdapterQuotaExceededError)
    assert isinstance(_map_tushare_error(Exception("每分钟频率超限"), "x"), AdapterQuotaExceededError)
    assert isinstance(_map_tushare_error(Exception("something weird"), "x"), AdapterDataError)


def test_tushare_session_without_token_raises_auth_error() -> None:
    with (
        patch("app.adapters.tushare_adapter.settings", SimpleNamespace(tushare_token=None)),
        pytest.raises(AdapterAuthError),
        tushare_session(),
    ):
        pass


def test_tushare_session_passes_token_without_writing_home_file() -> None:
    pro = MagicMock()
    tushare = SimpleNamespace(pro_api=MagicMock(return_value=pro))
    with (
        patch("app.adapters.tushare_adapter.settings", SimpleNamespace(tushare_token="secret-token")),
        patch.dict("sys.modules", {"tushare": tushare}),
        tushare_session() as result,
    ):
        assert result is pro
    tushare.pro_api.assert_called_once_with("secret-token")


def _fake_classify_df(level: str) -> pd.DataFrame:
    if level == "L1":
        return pd.DataFrame([
            {
                "index_code": "801010.SI",
                "industry_code": "SW801010",
                "industry_name": "农林牧渔",
                "parent_code": None,
                "is_pub": "Y",
            },
        ])
    if level == "L2":
        return pd.DataFrame([
            {
                "index_code": "801011.SI",
                "industry_code": "SW801011",
                "industry_name": "种植业",
                "parent_code": "SW801010",
                "is_pub": "Y",
            },
        ])
    return pd.DataFrame([
        {
            "index_code": "801012.SI",
            "industry_code": "SW801012",
            "industry_name": "粮食种植",
            "parent_code": "SW801011",
            "is_pub": "Y",
        },
    ])


def test_fetch_sw_classify_walks_all_levels() -> None:
    pro = MagicMock()
    pro.index_classify.side_effect = lambda level, src: _fake_classify_df(level)
    rows = fetch_sw_classify(pro)
    assert len(rows) == 3
    levels = {r.level for r in rows}
    assert levels == {"L1", "L2", "L3"}
    l2 = next(r for r in rows if r.level == "L2")
    assert l2.parent_code == "SW801010"


def test_fetch_sw_classify_maps_permission_error_to_auth() -> None:
    pro = MagicMock()
    pro.index_classify.side_effect = Exception("接口权限未开通")
    with pytest.raises(AdapterAuthError):
        fetch_sw_classify(pro)


def test_fetch_sw_classify_maps_points_error_to_quota() -> None:
    pro = MagicMock()
    pro.index_classify.side_effect = Exception("积分不足")
    with pytest.raises(AdapterQuotaExceededError):
        fetch_sw_classify(pro)


def test_fetch_sw_members_uses_bulk_endpoint_when_available() -> None:
    pro = MagicMock()
    # `index_member_all` returns pre-hydrated rows with l3_code (not index_code).
    # Two pages: first at capacity forces a second call; second is empty → stop.
    pro.index_member_all.side_effect = [
        pd.DataFrame([
            {"ts_code": "600123.SH", "l3_code": "801012.SI", "in_date": "20200101", "out_date": None},
            {"ts_code": "600124.SH", "l3_code": "801012.SI", "in_date": "20210101", "out_date": None},
        ]),
        pd.DataFrame(),
    ]
    rows = fetch_sw_members(pro, ["801012.SI"])
    assert len(rows) == 2
    assert {r.ts_code for r in rows} == {"600123.SH", "600124.SH"}
    assert all(r.l3_index_code == "801012.SI" for r in rows)
    pro.index_member.assert_not_called()


def test_fetch_trade_cal_maps_dates_and_open_flag() -> None:
    pro = MagicMock()
    pro.trade_cal.return_value = pd.DataFrame([
        {"cal_date": "20260708", "is_open": "1"},
        {"cal_date": "20260709", "is_open": "0"},
    ])
    rows = fetch_trade_cal(pro, date(2026, 7, 8), date(2026, 7, 9))
    assert [row.cal_date for row in rows] == [date(2026, 7, 8), date(2026, 7, 9)]
    assert [row.is_open for row in rows] == [True, False]


def test_fetch_daily_by_trade_date_maps_numeric_fields() -> None:
    pro = MagicMock()
    pro.daily.return_value = pd.DataFrame([
        {
            "ts_code": "000001.SZ",
            "trade_date": "20260708",
            "open": "10.1",
            "high": "10.5",
            "low": "9.8",
            "close": "10.2",
            "pre_close": "10.0",
            "pct_chg": "2.0",
            "vol": "123.45",
            "amount": "678.9",
        },
    ])
    rows = fetch_daily_by_trade_date(pro, date(2026, 7, 8))
    assert len(rows) == 1
    assert rows[0].ts_code == "000001.SZ"
    assert rows[0].close is not None
    assert str(rows[0].close) == "10.2"


def test_fetch_daily_basic_and_adj_factor() -> None:
    pro = MagicMock()
    pro.daily_basic.return_value = pd.DataFrame([
        {
            "ts_code": "000001.SZ",
            "trade_date": "20260708",
            "turnover_rate": "1.23",
            "turnover_rate_f": "1.50",
            "total_share": "1000",
            "float_share": "800",
            "free_share": "700",
            "total_mv": "120000",
            "circ_mv": "96000",
        },
    ])
    pro.adj_factor.return_value = pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "20260708", "adj_factor": "1.23456789"},
    ])

    daily_basic = fetch_daily_basic_by_trade_date(pro, date(2026, 7, 8))
    adj = fetch_adj_factor_by_trade_date(pro, date(2026, 7, 8))

    assert str(daily_basic[0].total_mv) == "120000"
    assert str(adj[0].adj_factor) == "1.23456789"


def test_fetch_sw_members_falls_back_when_bulk_missing() -> None:
    pro = MagicMock()
    del pro.index_member_all
    pro.index_member.return_value = pd.DataFrame([
        {"con_code": "600200.SH", "in_date": "20220101", "out_date": None},
    ])
    rows = fetch_sw_members(pro, ["801012.SI", "801013.SI"])
    assert pro.index_member.call_count == 2
    # Same ts_code but distinct L3 index_codes → two distinct membership rows.
    assert len(rows) == 2
    assert {r.l3_index_code for r in rows} == {"801012.SI", "801013.SI"}
    assert {r.ts_code for r in rows} == {"600200.SH"}


def test_rows_from_member_df_skips_missing_ids() -> None:
    df = pd.DataFrame([
        {"con_code": "", "index_code": "801010.SI"},
        {"con_code": "600001.SH", "index_code": "801010.SI"},
    ])
    rows = _rows_from_member_df(df)
    assert len(rows) == 1
    assert rows[0].ts_code == "600001.SH"


def test_rate_limited_error_triggers_retry_then_gives_up() -> None:
    """频率-超限 messages should back off once, then be surfaced as QuotaExceeded."""
    import app.adapters.tushare_adapter as adapter

    pro = MagicMock()
    pro.index_classify.side_effect = Exception("频率超限")

    with patch.object(adapter.time, "sleep") as sleep_mock:
        with pytest.raises(AdapterQuotaExceededError):
            fetch_sw_classify(pro)
        # sleep called at least once for the 60s backoff (plus any rate gate calls).
        assert sleep_mock.called


def test_classify_row_type_is_frozen() -> None:
    row = SWClassifyRow(
        index_code="801010.SI",
        industry_code="SW801010",
        industry_name="农林牧渔",
        level="L1",
        parent_code=None,
        is_pub=True,
        src="SW2021",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.industry_name = "changed"  # type: ignore[misc]
