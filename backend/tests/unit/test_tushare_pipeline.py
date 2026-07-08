"""Unit tests for Tushare data pipeline mapping helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.adapters.tushare_types import TushareDailyBasicRow, TushareDailyRow, TushareStockBasicRow
from app.data_service.tushare_pipeline import (
    SOURCE_TUSHARE_DAILY_BASIC,
    _hfq,
    _qfq,
    _to_kline_row,
    _to_market_cap_row,
    _to_stock_repo_row,
)


def test_stock_basic_mapping_keeps_frontend_compatible_fields() -> None:
    row = TushareStockBasicRow(
        ts_code="600000.SH",
        symbol="600000",
        name="浦发银行",
        area="上海",
        industry="银行",
        market="主板",
        exchange="SSE",
        list_status="L",
        list_date=date(1999, 11, 10),
        delist_date=None,
    )

    mapped = _to_stock_repo_row(row, "unit")

    assert mapped.bs_code == "sh.600000"
    assert mapped.market == "SSE"
    assert mapped.is_bj is False
    assert mapped.is_common is True
    assert mapped.updated_by == "unit"


def test_daily_mapping_converts_tushare_units() -> None:
    daily = TushareDailyRow(
        ts_code="000001.SZ",
        trade_date=date(2026, 7, 8),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        pre_close=Decimal("10.0"),
        pct_chg=Decimal("5.0"),
        vol=Decimal("123"),
        amount=Decimal("456"),
    )
    daily_basic = TushareDailyBasicRow(
        ts_code="000001.SZ",
        trade_date=date(2026, 7, 8),
        turnover_rate=Decimal("1.25"),
        turnover_rate_f=None,
        total_share=None,
        float_share=None,
        free_share=None,
        total_mv=None,
        circ_mv=None,
    )

    mapped = _to_kline_row(daily, daily_basic, None)

    assert mapped.volume == Decimal("12300")
    assert mapped.amount == Decimal("456000")
    assert mapped.turn == Decimal("1.25")
    assert mapped.close_raw == Decimal("10.5")


def test_daily_basic_mapping_converts_market_cap_units() -> None:
    daily = TushareDailyRow(
        ts_code="000001.SZ",
        trade_date=date(2026, 7, 8),
        open=None,
        high=None,
        low=None,
        close=Decimal("10.5"),
        pre_close=None,
        pct_chg=None,
        vol=None,
        amount=None,
    )
    daily_basic = TushareDailyBasicRow(
        ts_code="000001.SZ",
        trade_date=date(2026, 7, 8),
        turnover_rate=None,
        turnover_rate_f=None,
        total_share=Decimal("1000"),
        float_share=Decimal("800"),
        free_share=Decimal("700"),
        total_mv=Decimal("120000"),
        circ_mv=Decimal("96000"),
    )

    mapped = _to_market_cap_row(daily_basic, daily)

    assert mapped.market_cap_source == SOURCE_TUSHARE_DAILY_BASIC
    assert mapped.total_market_cap == Decimal("1200000000")
    assert mapped.circ_market_cap == Decimal("960000000")
    assert mapped.total_share == Decimal("10000000")
    assert mapped.liqa_share == Decimal("8000000")
    assert mapped.snapshot_close == Decimal("10.5")


def test_adjustment_formula_matches_tushare_pro_bar_shape() -> None:
    assert _hfq(Decimal("10"), Decimal("2")) == Decimal("20")
    assert _qfq(Decimal("10"), Decimal("2"), Decimal("4")) == Decimal("5")
    assert _qfq(None, Decimal("2"), Decimal("4")) is None
