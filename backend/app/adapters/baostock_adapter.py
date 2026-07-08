"""baostock adapter — 主数据源，只做外部数据获取，不写 DB。

对齐 prompt/reference/baostock_cheatsheet.md：
- adjustflag: 1=后复权 / 2=前复权 / 3=不复权
- tradestatus: 1=交易 / 0=停牌（停牌日价格字段为空字符串 → 转 None）
- 每次调用用 baostock_session context manager 包裹 login/logout
"""

from __future__ import annotations

import logging
import signal
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

import baostock as bs
import pandas as pd

from app.adapters.baostock_types import (
    KLinePriceGroup,
    StockBasicRow,
    TradeCalRow,
)
from app.core.errors import (
    AdapterAuthError,
    AdapterConnectionError,
    AdapterDataError,
    AdapterQuotaExceededError,
)

logger = logging.getLogger(__name__)

AdjustFlag = Literal["1", "2", "3"]  # 1=hfq, 2=qfq, 3=raw
ADJUST_HFQ: AdjustFlag = "1"
ADJUST_QFQ: AdjustFlag = "2"
ADJUST_RAW: AdjustFlag = "3"

# baostock error code returned when the daily 50k-call quota is exhausted.
BAOSTOCK_QUOTA_EXCEEDED_CODE = "10001007"
BAOSTOCK_NOT_LOGGED_IN_CODE = "10001001"
BAOSTOCK_NETWORK_RECV_ERROR_CODE = "10002007"


@contextmanager
def baostock_session() -> Iterator[None]:
    """Context manager wrapping bs.login/bs.logout with error mapping."""
    try:
        rs = bs.login()
    except Exception as exc:
        raise AdapterConnectionError(f"baostock login network error: {exc}") from exc

    if getattr(rs, "error_code", "1") != "0":
        if rs.error_code == BAOSTOCK_QUOTA_EXCEEDED_CODE:
            raise AdapterQuotaExceededError(
                f"baostock login quota exceeded: code={rs.error_code} msg={rs.error_msg}"
            )
        raise AdapterAuthError(
            f"baostock login failed: code={rs.error_code} msg={rs.error_msg}"
        )
    try:
        yield
    finally:
        try:
            bs.logout()
        except Exception as exc:
            logger.warning("baostock logout error: %s", exc)


def reconnect() -> None:
    """Re-establish the baostock socket after a connection error or timeout.

    The broken socket is closed forcibly before re-login so that stale state
    cannot contaminate the new connection. logout() itself may fail on a broken
    socket — that's expected and silently ignored.
    """
    import baostock.common.context as _ctx
    # Force-close the broken socket directly, bypassing logout's own recv
    try:
        sock = getattr(_ctx, "default_socket", None)
        if sock is not None:
            with suppress(Exception):
                sock.close()
            _ctx.default_socket = None
    except Exception:
        pass
    # Discard any lingering logout attempt
    with suppress(Exception):
        bs.logout()
    rs = bs.login()
    if getattr(rs, "error_code", "1") != "0":
        if rs.error_code == BAOSTOCK_QUOTA_EXCEEDED_CODE:
            raise AdapterQuotaExceededError(
                f"baostock reconnect quota exceeded: code={rs.error_code} msg={rs.error_msg}"
            )
        raise AdapterConnectionError(
            f"baostock reconnect failed: code={rs.error_code} msg={rs.error_msg}"
        )
    logger.info("baostock reconnected successfully")


def _bs_to_ts_code(bs_code: str) -> str:
    """`sh.600000` → `600000.SH`, `sz.000001` → `000001.SZ`, `bj.430047` → `430047.BJ`."""
    prefix, num = bs_code.split(".", 1)
    return f"{num}.{prefix.upper()}"


def _market_from_bs(bs_code: str) -> str:
    return bs_code.split(".", 1)[0].upper()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_decimal(value: str | None) -> Decimal | None:
    """Empty string / None → None; suspended-day rows return empty prices from baostock."""
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _rs_to_df(rs, endpoint: str) -> pd.DataFrame:
    """Consume a baostock ResultSet into a DataFrame; raise AdapterDataError on failure."""
    error_code = getattr(rs, "error_code", "1")
    if error_code != "0":
        if error_code == BAOSTOCK_QUOTA_EXCEEDED_CODE:
            raise AdapterQuotaExceededError(
                f"baostock {endpoint} quota exceeded: code={error_code} msg={rs.error_msg}"
            )
        if error_code in (BAOSTOCK_NOT_LOGGED_IN_CODE, BAOSTOCK_NETWORK_RECV_ERROR_CODE):
            raise AdapterConnectionError(
                f"baostock {endpoint} connection lost: code={error_code} msg={rs.error_msg}"
            )
        raise AdapterDataError(
            f"baostock {endpoint} failed: code={error_code} msg={rs.error_msg}"
        )
    rows: list[list[str]] = []
    while rs.next():
        rows.append(rs.get_row_data())
    return pd.DataFrame(rows, columns=rs.fields)


def fetch_stock_basic(bs_code: str | None = None) -> list[StockBasicRow]:
    """Fetch stock basic info. `bs_code=None` pulls the whole market."""
    kwargs = {"code": bs_code} if bs_code else {}
    rs = bs.query_stock_basic(**kwargs)
    df = _rs_to_df(rs, "query_stock_basic")

    result: list[StockBasicRow] = []
    for _, row in df.iterrows():
        code = row["code"]
        result.append(
            StockBasicRow(
                ts_code=_bs_to_ts_code(code),
                bs_code=code,
                name=row["code_name"],
                market=_market_from_bs(code),
                list_date=_parse_date(row.get("ipoDate") or None),
                delist_date=_parse_date(row.get("outDate") or None),
                is_bj=code.startswith("bj."),
                is_common=str(row.get("type", "")) == "1",
            )
        )
    return result


def fetch_trade_cal(start_date: date, end_date: date) -> list[TradeCalRow]:
    """Fetch trade calendar for the given inclusive date range."""
    rs = bs.query_trade_dates(
        start_date=start_date.isoformat(), end_date=end_date.isoformat()
    )
    df = _rs_to_df(rs, "query_trade_dates")

    result: list[TradeCalRow] = []
    for _, row in df.iterrows():
        result.append(
            TradeCalRow(
                cal_date=date.fromisoformat(row["calendar_date"]),
                is_open=str(row["is_trading_day"]) == "1",
            )
        )
    return result


_KLINE_FIELDS = (
    "date,code,open,high,low,close,preclose,"
    "volume,amount,turn,tradestatus,pctChg,isST"
)

# Per-call timeout for fetch_kline (seconds). baostock has no built-in socket timeout;
# a hung recv() blocks forever. SIGALRM interrupts it after this many seconds.
_FETCH_KLINE_TIMEOUT = 60


@contextmanager
def _timeout(seconds: int) -> Iterator[None]:
    """SIGALRM-based timeout context. Only safe on the main thread (Linux)."""
    def _handler(signum, frame):
        raise AdapterConnectionError(f"baostock fetch_kline timed out after {seconds}s")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def fetch_kline(
    bs_code: str,
    start_date: date,
    end_date: date,
    adjustflag: AdjustFlag = ADJUST_QFQ,
) -> list[KLinePriceGroup]:
    """Fetch daily K-line for a single stock in one adjust-flag mode.

    Suspended days (tradestatus=0) are returned with all price fields = None.
    Raises AdapterConnectionError if the baostock socket hangs for > 60s.
    """
    with _timeout(_FETCH_KLINE_TIMEOUT):
        rs = bs.query_history_k_data_plus(
            bs_code,
            _KLINE_FIELDS,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            frequency="d",
            adjustflag=adjustflag,
        )
        df = _rs_to_df(rs, "query_history_k_data_plus")

    result: list[KLinePriceGroup] = []
    ts_code = _bs_to_ts_code(bs_code)
    for _, row in df.iterrows():
        result.append(
            KLinePriceGroup(
                ts_code=ts_code,
                trade_date=date.fromisoformat(row["date"]),
                open=_parse_decimal(row.get("open")),
                high=_parse_decimal(row.get("high")),
                low=_parse_decimal(row.get("low")),
                close=_parse_decimal(row.get("close")),
                preclose=_parse_decimal(row.get("preclose")),
                volume=_parse_decimal(row.get("volume")),
                amount=_parse_decimal(row.get("amount")),
                turn=_parse_decimal(row.get("turn")),
                pct_chg=_parse_decimal(row.get("pctChg")),
                trade_status=int(row.get("tradestatus") or "0"),
                is_st=str(row.get("isST", "0")) == "1",
            )
        )
    return result
