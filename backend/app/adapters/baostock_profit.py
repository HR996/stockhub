"""baostock profit / capital data — 独立于主 adapter，供市值合成使用。

来自 `bs.query_profit_data`：字段含 `pubDate / statDate / totalShare / liqaShare` 等。
`totalShare` / `liqaShare` 单位为**股**（不是万股）。部分股票（如若干北交所）无 profit 记录，
在这种情形下返回 None 由调用方决定是否 mark 为 `baostock_missing`。
"""

from __future__ import annotations

import baostock as bs

# Reuse baostock_adapter's helpers to keep parsing consistent.
from app.adapters.baostock_adapter import _parse_date, _parse_decimal, _rs_to_df
from app.adapters.baostock_types import ProfitDataRow


def fetch_profit_data(bs_code: str, year: int, quarter: int) -> ProfitDataRow | None:
    """Fetch quarterly profit / capital data for a single stock.

    Returns None when the endpoint has no row for that stock/quarter.
    Raises AdapterDataError (via _rs_to_df) if baostock reports a non-zero error code.
    """
    rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
    df = _rs_to_df(rs, "query_profit_data")
    if df.empty:
        return None
    row = df.iloc[-1]  # baostock returns 0 or 1 row for a single (code, year, quarter)
    return ProfitDataRow(
        bs_code=bs_code,
        pub_date=_parse_date(row.get("pubDate") or None),
        stat_date=_parse_date(row.get("statDate") or None),
        total_share=_parse_decimal(row.get("totalShare")),
        liqa_share=_parse_decimal(row.get("liqaShare")),
    )
