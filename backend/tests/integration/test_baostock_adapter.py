"""P1-03 / P1-04 — Integration tests hitting real baostock API.

Marked `integration` — skip these in CI unless network access is available:
    pytest -m "not integration"

Uses the session-wide `bs_session` fixture from tests/conftest.py — one login per
pytest process to avoid baostock's blacklist on repeated anonymous logins
(`error_code=10001011: 黑名单用户`).
"""

from __future__ import annotations

from datetime import date

import pytest

from app.adapters.baostock_adapter import (
    ADJUST_HFQ,
    ADJUST_QFQ,
    ADJUST_RAW,
    fetch_kline,
    fetch_stock_basic,
    fetch_trade_cal,
)

pytestmark = pytest.mark.integration


def test_fetch_stock_basic_single_stock(bs_session) -> None:
    rows = fetch_stock_basic("sh.600000")
    assert len(rows) == 1
    row = rows[0]
    assert row.ts_code == "600000.SH"
    assert row.bs_code == "sh.600000"
    assert row.market == "SH"
    assert row.is_bj is False
    assert row.name  # non-empty
    assert row.list_date is not None


def test_fetch_trade_cal_range(bs_session) -> None:
    rows = fetch_trade_cal(date(2024, 1, 1), date(2024, 1, 31))
    assert len(rows) == 31
    jan1 = next(r for r in rows if r.cal_date == date(2024, 1, 1))
    assert jan1.is_open is False
    jan2 = next(r for r in rows if r.cal_date == date(2024, 1, 2))
    assert jan2.is_open is True


def test_fetch_kline_qfq_returns_prices(bs_session) -> None:
    rows = fetch_kline(
        "sh.600000",
        date(2024, 1, 2),
        date(2024, 1, 12),
        adjustflag=ADJUST_QFQ,
    )
    assert len(rows) >= 1
    row = rows[0]
    assert row.ts_code == "600000.SH"
    assert row.trade_status == 1
    assert row.close is not None and row.close > 0
    assert row.volume is not None


def test_fetch_kline_three_adjust_flags_same_date_range(bs_session) -> None:
    """All three adjust flags should return the same set of trade dates."""
    raw = fetch_kline("sh.600000", date(2024, 1, 2), date(2024, 1, 12), ADJUST_RAW)
    qfq = fetch_kline("sh.600000", date(2024, 1, 2), date(2024, 1, 12), ADJUST_QFQ)
    hfq = fetch_kline("sh.600000", date(2024, 1, 2), date(2024, 1, 12), ADJUST_HFQ)

    dates_raw = [r.trade_date for r in raw]
    dates_qfq = [r.trade_date for r in qfq]
    dates_hfq = [r.trade_date for r in hfq]
    assert dates_raw == dates_qfq == dates_hfq
    assert raw[0].close is not None
    assert qfq[0].close is not None
    assert hfq[0].close is not None


def test_fetch_profit_data_returns_total_share(bs_session) -> None:
    """P1-04 — real baostock profit_data probe for a stable large-cap stock."""
    from app.adapters.baostock_profit import fetch_profit_data

    row = fetch_profit_data("sh.600000", year=2024, quarter=4)
    assert row is not None
    assert row.bs_code == "sh.600000"
    assert row.total_share is not None
    assert row.liqa_share is not None
    # 浦发银行 A 股 293 亿股左右；宽区间断言避免季度间小幅浮动
    assert 2e10 < float(row.total_share) < 4e10
