"""baostock adapter DTOs — pure data structures returned by the adapter.

Kept in a separate module so services / tests can import types without triggering
the baostock library import at module load.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class StockBasicRow:
    ts_code: str          # e.g. 600000.SH
    bs_code: str          # e.g. sh.600000
    name: str
    market: str           # SH / SZ / BJ
    list_date: date | None
    delist_date: date | None
    is_bj: bool
    is_common: bool       # baostock type == '1'


@dataclass(frozen=True)
class TradeCalRow:
    cal_date: date
    is_open: bool


@dataclass(frozen=True)
class KLinePriceGroup:
    """A single-adjustflag price row from baostock. Callers merge across adjust flags."""

    ts_code: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    preclose: Decimal | None
    volume: Decimal | None
    amount: Decimal | None
    turn: Decimal | None
    pct_chg: Decimal | None
    trade_status: int      # 1 交易 / 0 停牌
    is_st: bool


@dataclass(frozen=True)
class ProfitDataRow:
    """One quarter of profit / capital data from baostock query_profit_data.

    Only fields we consume in v1 are exposed. `total_share` / `liqa_share` are in **shares**
    (not 万股); v1 uses these to synthesize latest market cap = total_share × close_at_snapshot.
    """

    bs_code: str
    pub_date: date | None       # 财报公告日
    stat_date: date | None      # 财报统计截止日（季末）
    total_share: Decimal | None
    liqa_share: Decimal | None
