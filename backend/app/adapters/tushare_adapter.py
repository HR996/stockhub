"""Tushare Pro adapter — Shenwan (SW2021) industry classification data source.

Only fetches data; never writes DB. Errors are mapped to the shared AdapterError
taxonomy (AdapterAuthError / AdapterQuotaExceededError / AdapterDataError).

Endpoints used:
- `pro.index_classify(level, src='SW2021')` for the L1/L2/L3 catalog
- `pro.index_member_all(l1_code, l2_code, l3_code, ...)` for stock membership
  (falls back to per-index `pro.index_member(index_code=...)` if unavailable)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from app.adapters.tushare_types import (
    SWClassifyRow,
    SWMemberRow,
    TushareAdjFactorRow,
    TushareDailyBasicRow,
    TushareDailyRow,
    TushareStockBasicRow,
    TushareTradeCalRow,
)
from app.core.config import settings
from app.core.errors import (
    AdapterAuthError,
    AdapterDataError,
    AdapterQuotaExceededError,
)

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

SW2021_SRC = "SW2021"
_LEVELS: tuple[str, ...] = ("L1", "L2", "L3")

# Tushare 2000-tier default: ~200 req/min. Leave slack.
_MIN_INTERVAL_SECONDS = 0.35
_RATE_LIMIT_BACKOFF_SECONDS = 60
# index_member_all page size — Tushare returns at most ~3000 rows/call at 2000-tier.
_INDEX_MEMBER_ALL_PAGE_SIZE = 3000
_INDEX_MEMBER_ALL_MAX_ROWS = 30_000  # sanity cap; the A-share market is ~5-6k stocks
_DAILY_PAGE_SIZE = 6000
_DAILY_MAX_ROWS = 30_000


@contextmanager
def tushare_session() -> Iterator[Any]:
    """Yield a `tushare.pro_api()` handle after setting the token.

    Raises AdapterAuthError when TUSHARE_TOKEN is unset or Tushare rejects the token.
    """
    token = settings.tushare_token
    if not token:
        raise AdapterAuthError("TUSHARE_TOKEN is not set — cannot initialize tushare session")
    try:
        import tushare as ts
    except ImportError as exc:
        raise AdapterAuthError(f"tushare library not installed: {exc}") from exc
    try:
        ts.set_token(token)
        pro = ts.pro_api()
    except Exception as exc:
        raise _map_tushare_error(exc, "pro_api init") from exc
    yield pro


def _map_tushare_error(exc: BaseException, endpoint: str) -> Exception:
    """Map a raw tushare Exception to the AdapterError taxonomy by message content."""
    msg = str(exc)
    if any(k in msg for k in ("权限", "未开通", "无权", "token", "IP数量超限")):
        return AdapterAuthError(f"tushare {endpoint} auth error: {msg}")
    if any(k in msg for k in ("积分", "点数", "quota")):
        return AdapterQuotaExceededError(f"tushare {endpoint} quota/points error: {msg}")
    if any(k in msg for k in ("频率", "每分钟", "rate limit", "太快")):
        return AdapterQuotaExceededError(f"tushare {endpoint} rate-limited: {msg}")
    return AdapterDataError(f"tushare {endpoint} failed: {msg}")


class _RateGate:
    """Minimal token-bucket-ish gate: enforces a minimum interval between calls."""

    def __init__(self, min_interval_seconds: float) -> None:
        self._min = min_interval_seconds
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self._min:
            time.sleep(self._min - elapsed)
        self._last = time.monotonic()


def _call_with_retry(
    fn: Any, endpoint: str, gate: _RateGate, **kwargs: Any
) -> pd.DataFrame:
    """Rate-limited single call with one retry on 频率 errors after a 60s backoff."""
    for attempt in (1, 2):
        gate.wait()
        try:
            df = fn(**kwargs)
        except Exception as exc:
            mapped = _map_tushare_error(exc, endpoint)
            if isinstance(mapped, AdapterQuotaExceededError) and "rate-limited" in str(mapped) and attempt == 1:
                logger.warning("tushare %s rate-limited, backing off %ss", endpoint, _RATE_LIMIT_BACKOFF_SECONDS)
                time.sleep(_RATE_LIMIT_BACKOFF_SECONDS)
                continue
            raise mapped from exc
        if df is None:
            raise AdapterDataError(f"tushare {endpoint} returned None")
        return df
    raise AdapterQuotaExceededError(f"tushare {endpoint} still rate-limited after retry")


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    if s in ("1", "Y", "True", "true", "TRUE", "是"):
        return True
    if s in ("0", "N", "False", "false", "FALSE", "否"):
        return False
    return None


def _parse_tushare_date(value: Any) -> date | None:
    """Tushare dates are `YYYYMMDD` strings; empty/None → None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    # ISO fallback
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _date_arg(day: date | None) -> str | None:
    return None if day is None else day.strftime("%Y%m%d")


def _paged_by_offset(
    fn: Any,
    endpoint: str,
    gate: _RateGate,
    *,
    limit: int = _DAILY_PAGE_SIZE,
    max_rows: int = _DAILY_MAX_ROWS,
    **kwargs: Any,
) -> pd.DataFrame:
    """Fetch endpoints that support offset/limit. Concatenate pages defensively."""
    import pandas as pd

    pages: list[pd.DataFrame] = []
    offset = 0
    while True:
        df = _call_with_retry(
            fn,
            endpoint=f"{endpoint}[offset={offset}]",
            gate=gate,
            offset=offset,
            limit=limit,
            **kwargs,
        )
        if df.empty:
            break
        pages.append(df)
        if len(df) < limit:
            break
        offset += limit
        if offset >= max_rows:
            logger.warning("tushare %s reached hard row cap %d", endpoint, max_rows)
            break
    if not pages:
        return pd.DataFrame()
    return pd.concat(pages, ignore_index=True)


def fetch_stock_basic(pro: Any) -> list[TushareStockBasicRow]:
    """Fetch Tushare `stock_basic` for listed, delisted and paused A-share stocks."""
    gate = _RateGate(_MIN_INTERVAL_SECONDS)
    out: list[TushareStockBasicRow] = []
    for status in ("L", "D", "P"):
        df = _call_with_retry(
            pro.stock_basic,
            endpoint=f"stock_basic:{status}",
            gate=gate,
            exchange="",
            list_status=status,
            fields=(
                "ts_code,symbol,name,area,industry,market,exchange,"
                "list_status,list_date,delist_date"
            ),
        )
        for _, r in df.iterrows():
            ts_code = r.get("ts_code")
            if not ts_code:
                continue
            out.append(
                TushareStockBasicRow(
                    ts_code=str(ts_code),
                    symbol=str(r.get("symbol") or ""),
                    name=str(r.get("name") or "").strip(),
                    area=_str_or_none(r.get("area")),
                    industry=_str_or_none(r.get("industry")),
                    market=_str_or_none(r.get("market")),
                    exchange=_str_or_none(r.get("exchange")),
                    list_status=_str_or_none(r.get("list_status")) or status,
                    list_date=_parse_tushare_date(r.get("list_date")),
                    delist_date=_parse_tushare_date(r.get("delist_date")),
                )
            )
    out.sort(key=lambda row: row.ts_code)
    return out


def fetch_trade_cal(pro: Any, start_date: date, end_date: date, exchange: str = "SSE") -> list[TushareTradeCalRow]:
    """Fetch Tushare `trade_cal` rows in [start_date, end_date]."""
    gate = _RateGate(_MIN_INTERVAL_SECONDS)
    df = _call_with_retry(
        pro.trade_cal,
        endpoint="trade_cal",
        gate=gate,
        exchange=exchange,
        start_date=_date_arg(start_date),
        end_date=_date_arg(end_date),
    )
    rows: list[TushareTradeCalRow] = []
    for _, r in df.iterrows():
        cal_date = _parse_tushare_date(r.get("cal_date"))
        if cal_date is None:
            continue
        rows.append(TushareTradeCalRow(cal_date=cal_date, is_open=bool(_parse_bool(r.get("is_open")))))
    rows.sort(key=lambda row: row.cal_date)
    return rows


def fetch_daily_by_trade_date(pro: Any, trade_date: date) -> list[TushareDailyRow]:
    """Fetch unadjusted A-share daily bars for one trading date."""
    gate = _RateGate(_MIN_INTERVAL_SECONDS)
    df = _paged_by_offset(
        pro.daily,
        endpoint=f"daily:{trade_date.isoformat()}",
        gate=gate,
        trade_date=_date_arg(trade_date),
    )
    rows: list[TushareDailyRow] = []
    for _, r in df.iterrows():
        parsed_date = _parse_tushare_date(r.get("trade_date"))
        ts_code = r.get("ts_code")
        if not ts_code or parsed_date is None:
            continue
        rows.append(
            TushareDailyRow(
                ts_code=str(ts_code),
                trade_date=parsed_date,
                open=_parse_decimal(r.get("open")),
                high=_parse_decimal(r.get("high")),
                low=_parse_decimal(r.get("low")),
                close=_parse_decimal(r.get("close")),
                pre_close=_parse_decimal(r.get("pre_close")),
                pct_chg=_parse_decimal(r.get("pct_chg")),
                vol=_parse_decimal(r.get("vol")),
                amount=_parse_decimal(r.get("amount")),
            )
        )
    rows.sort(key=lambda row: row.ts_code)
    return rows


def fetch_daily_basic_by_trade_date(pro: Any, trade_date: date) -> list[TushareDailyBasicRow]:
    """Fetch Tushare `daily_basic` rows for one trading date."""
    gate = _RateGate(_MIN_INTERVAL_SECONDS)
    df = _paged_by_offset(
        pro.daily_basic,
        endpoint=f"daily_basic:{trade_date.isoformat()}",
        gate=gate,
        trade_date=_date_arg(trade_date),
        fields=(
            "ts_code,trade_date,turnover_rate,turnover_rate_f,total_share,"
            "float_share,free_share,total_mv,circ_mv"
        ),
    )
    rows: list[TushareDailyBasicRow] = []
    for _, r in df.iterrows():
        parsed_date = _parse_tushare_date(r.get("trade_date"))
        ts_code = r.get("ts_code")
        if not ts_code or parsed_date is None:
            continue
        rows.append(
            TushareDailyBasicRow(
                ts_code=str(ts_code),
                trade_date=parsed_date,
                turnover_rate=_parse_decimal(r.get("turnover_rate")),
                turnover_rate_f=_parse_decimal(r.get("turnover_rate_f")),
                total_share=_parse_decimal(r.get("total_share")),
                float_share=_parse_decimal(r.get("float_share")),
                free_share=_parse_decimal(r.get("free_share")),
                total_mv=_parse_decimal(r.get("total_mv")),
                circ_mv=_parse_decimal(r.get("circ_mv")),
            )
        )
    rows.sort(key=lambda row: row.ts_code)
    return rows


def fetch_adj_factor_by_trade_date(pro: Any, trade_date: date) -> list[TushareAdjFactorRow]:
    """Fetch Tushare `adj_factor` rows for one trading date."""
    gate = _RateGate(_MIN_INTERVAL_SECONDS)
    df = _paged_by_offset(
        pro.adj_factor,
        endpoint=f"adj_factor:{trade_date.isoformat()}",
        gate=gate,
        trade_date=_date_arg(trade_date),
    )
    rows: list[TushareAdjFactorRow] = []
    for _, r in df.iterrows():
        parsed_date = _parse_tushare_date(r.get("trade_date"))
        adj_factor = _parse_decimal(r.get("adj_factor"))
        ts_code = r.get("ts_code")
        if not ts_code or parsed_date is None or adj_factor is None:
            continue
        rows.append(TushareAdjFactorRow(ts_code=str(ts_code), trade_date=parsed_date, adj_factor=adj_factor))
    rows.sort(key=lambda row: row.ts_code)
    return rows


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def fetch_sw_classify(pro: Any, src: str = SW2021_SRC) -> list[SWClassifyRow]:
    """Fetch the full Shenwan L1/L2/L3 classification catalog.

    One API call per level. Returns rows sorted by (level, index_code) for stable output.
    """
    gate = _RateGate(_MIN_INTERVAL_SECONDS)
    rows: list[SWClassifyRow] = []
    for level in _LEVELS:
        df = _call_with_retry(
            pro.index_classify, endpoint=f"index_classify:{level}", gate=gate,
            level=level, src=src,
        )
        for _, r in df.iterrows():
            industry_code = r.get("industry_code")
            index_code = r.get("index_code")
            if industry_code is None or index_code is None:
                raise AdapterDataError(
                    f"tushare index_classify {level}: missing industry_code/index_code row: {dict(r)}"
                )
            parent_raw = r.get("parent_code")
            parent = None if parent_raw in (None, "", float("nan")) else str(parent_raw)
            rows.append(
                SWClassifyRow(
                    index_code=str(index_code),
                    industry_code=str(industry_code),
                    industry_name=str(r.get("industry_name", "")).strip(),
                    level=level,
                    parent_code=parent,
                    is_pub=_parse_bool(r.get("is_pub")),
                    src=src,
                )
            )
    rows.sort(key=lambda x: (x.level, x.index_code))
    return rows


def fetch_sw_members(pro: Any, l3_index_codes: list[str]) -> list[SWMemberRow]:
    """Fetch current (is_new='Y') stock membership for every L3 industry.

    Strategy:
    1. Try `pro.index_member_all(is_new='Y')` with offset-based pagination.
       Returns pre-hydrated rows (l1/l2/l3 codes + names), but this adapter only
       keeps the L3 code — the service re-hydrates uniformly from the classify
       catalog so both endpoints produce identical downstream rows.
    2. If the bulk endpoint is unavailable, fall back to per-L3
       `pro.index_member(index_code=..., is_new='Y')` (~350 calls).

    Returns rows deduplicated by (ts_code, l3_index_code).
    """
    gate = _RateGate(_MIN_INTERVAL_SECONDS)
    rows = _try_index_member_all(pro, gate)
    if rows is None:
        rows = _fetch_members_per_l3(pro, gate, l3_index_codes)
    seen: set[tuple[str, str]] = set()
    deduped: list[SWMemberRow] = []
    for row in rows:
        key = (row.ts_code, row.l3_index_code)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    deduped.sort(key=lambda x: (x.l3_index_code, x.ts_code))
    return deduped


def _try_index_member_all(pro: Any, gate: _RateGate) -> list[SWMemberRow] | None:
    """Attempt the bulk endpoint with pagination. Return None to signal fallback."""
    fn = getattr(pro, "index_member_all", None)
    if fn is None:
        return None
    out: list[SWMemberRow] = []
    offset = 0
    page_size = _INDEX_MEMBER_ALL_PAGE_SIZE
    while True:
        try:
            df = _call_with_retry(
                fn, endpoint=f"index_member_all[offset={offset}]", gate=gate,
                is_new="Y", offset=offset, limit=page_size,
            )
        except AdapterDataError as exc:
            if offset == 0:
                logger.warning("index_member_all unavailable, falling back per-L3: %s", exc)
                return None
            raise
        if df is None or df.empty:
            break
        out.extend(_rows_from_member_df(df))
        if len(df) < page_size:
            break
        offset += page_size
        if offset >= _INDEX_MEMBER_ALL_MAX_ROWS:
            logger.warning(
                "index_member_all reached hard row cap %d — aborting pagination",
                _INDEX_MEMBER_ALL_MAX_ROWS,
            )
            break
    return out if out else None


def _fetch_members_per_l3(
    pro: Any, gate: _RateGate, l3_index_codes: list[str]
) -> list[SWMemberRow]:
    """Loop over each L3 industry index_code and pull its current constituents."""
    fn = getattr(pro, "index_member", None)
    if fn is None:
        raise AdapterDataError("tushare pro_api exposes neither index_member_all nor index_member")
    out: list[SWMemberRow] = []
    for index_code in l3_index_codes:
        df = _call_with_retry(
            fn, endpoint=f"index_member:{index_code}", gate=gate,
            index_code=index_code, is_new="Y",
        )
        if df is None or df.empty:
            continue
        out.extend(_rows_from_member_df(df, default_index_code=index_code))
    return out


def _rows_from_member_df(df: pd.DataFrame, default_index_code: str | None = None) -> list[SWMemberRow]:
    """Convert a Tushare member DataFrame to SWMemberRow list.

    Handles both schemas:
      - `index_member_all`: columns include `ts_code`, `l3_code`, `l3_name`, `l1_code`, `l2_code`, ...
      - `index_member` (per-index): columns are `index_code`, `con_code`, ... (no name column)
    We keep ts_code + L3 index_code + L3 name (when available) + dates; the service
    re-hydrates L1/L2 uniformly from the classify catalog, and uses `l3_name` as a
    fallback key when `l3_index_code` isn't in the SW2021 catalog.
    """
    out: list[SWMemberRow] = []
    for _, r in df.iterrows():
        ts_code = r.get("ts_code") or r.get("con_code")
        idx = r.get("l3_code") or r.get("index_code") or default_index_code
        if not ts_code or not idx:
            continue
        l3_name_raw = r.get("l3_name")
        l3_name = str(l3_name_raw).strip() if l3_name_raw not in (None, "") else None
        out.append(
            SWMemberRow(
                ts_code=str(ts_code),
                l3_index_code=str(idx),
                in_date=_parse_tushare_date(r.get("in_date")),
                out_date=_parse_tushare_date(r.get("out_date")),
                l3_name=l3_name,
            )
        )
    return out
