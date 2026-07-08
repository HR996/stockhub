"""Tushare adapter DTOs — frozen dataclasses returned by tushare_adapter.

Isolated from the adapter module so services/tests can import types without
triggering the tushare library import at module load.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class TushareStockBasicRow:
    ts_code: str
    symbol: str
    name: str
    area: str | None
    industry: str | None
    market: str | None
    exchange: str | None
    list_status: str | None
    list_date: date | None
    delist_date: date | None


@dataclass(frozen=True)
class TushareTradeCalRow:
    cal_date: date
    is_open: bool


@dataclass(frozen=True)
class TushareDailyRow:
    ts_code: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    pre_close: Decimal | None
    pct_chg: Decimal | None
    vol: Decimal | None
    amount: Decimal | None


@dataclass(frozen=True)
class TushareDailyBasicRow:
    ts_code: str
    trade_date: date
    turnover_rate: Decimal | None
    turnover_rate_f: Decimal | None
    total_share: Decimal | None
    float_share: Decimal | None
    free_share: Decimal | None
    total_mv: Decimal | None
    circ_mv: Decimal | None


@dataclass(frozen=True)
class TushareAdjFactorRow:
    ts_code: str
    trade_date: date
    adj_factor: Decimal


@dataclass(frozen=True)
class SWClassifyRow:
    """One row from Tushare `index_classify` — a Shenwan L1/L2/L3 catalog entry.

    `parent_code` references the parent row's `industry_code` (not `index_code`).
    """

    index_code: str          # e.g. 801010.SI
    industry_code: str       # business code; parent_code references this
    industry_name: str
    level: str               # "L1" / "L2" / "L3"
    parent_code: str | None
    is_pub: bool | None
    src: str                 # "SW2021"


@dataclass(frozen=True)
class SWMemberRow:
    """One row from Tushare `index_member_all` / `index_member`.

    `l3_name` is populated by the bulk `index_member_all` endpoint but is None
    for the per-L3 fallback (`pro.index_member`) which doesn't return names.
    The service layer uses it as a fallback key when `l3_index_code` is not
    found in the SW2021 classify catalog (e.g. legacy SW2014 codes still
    returned by `index_member_all`).

    L1/L2 hydration is done in the service layer using classify results.
    """

    ts_code: str
    l3_index_code: str
    in_date: date | None
    out_date: date | None
    l3_name: str | None = None
