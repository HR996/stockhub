"""Latest market-cap synthesis service.

Combines:
1. baostock `query_profit_data` (latest quarterly `totalShare` / `liqaShare`)
2. `k_line_daily.close_raw` at a snapshot trading date

into rows written to `latest_market_cap` via MarketCapRepo. Callers own the baostock
session and DB session (the service does not manage session lifecycles).

Failure modes (per stock):
- No profit row (some BJ stocks) → `market_cap_source = 'baostock_missing'`
- No K-line row at snapshot date → `market_cap_source = 'baostock_missing'`
- Both present → `market_cap_source = 'baostock_synth'`

`market_cap` value is `total_share × close_raw` (naive multiplication; both sides in
their raw units — shares × yuan-per-share = yuan).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.adapters.baostock_profit import fetch_profit_data
from app.core.errors import AdapterQuotaExceededError
from app.repositories.kline_repo import KLineRepo
from app.repositories.market_cap_repo import MarketCapRepo, MarketCapUpsertRow

logger = logging.getLogger(__name__)


SOURCE_SYNTH = "baostock_synth"
SOURCE_MISSING = "baostock_missing"


@dataclass(frozen=True)
class SyncMarketCapResult:
    total: int
    synthesized: int
    missing: int


def _bs_code_from_ts(ts_code: str) -> str:
    """Convert '600000.SH' → 'sh.600000' (baostock format)."""
    num, market = ts_code.split(".", 1)
    return f"{market.lower()}.{num}"


def _quarter_of(day: date) -> tuple[int, int]:
    """Return (year, quarter) — the quarter to query for `day`.

    Uses the previous quarter to reduce the "no data yet published" window
    (a Q1 report is typically published in April; using the current quarter
    for a March snapshot would return an empty result for many stocks).
    """
    q = (day.month - 1) // 3 + 1
    if q == 1:
        return day.year - 1, 4
    return day.year, q - 1


def synthesize_for(
    ts_codes: list[str],
    snapshot_date: date,
    kline_repo: KLineRepo,
    market_cap_repo: MarketCapRepo,
) -> SyncMarketCapResult:
    """Compute latest market cap for `ts_codes` at `snapshot_date`.

    Assumes the caller has entered a `baostock_session` context and holds a DB session.
    Writes rows via `market_cap_repo.upsert_many`.
    """
    year, quarter = _quarter_of(snapshot_date)
    now = datetime.now(UTC)
    rows: list[MarketCapUpsertRow] = []
    synthesized = 0
    missing = 0

    for ts_code in ts_codes:
        bs_code = _bs_code_from_ts(ts_code)
        profit = None
        try:
            profit = fetch_profit_data(bs_code, year=year, quarter=quarter)
        except AdapterQuotaExceededError:
            logger.error("baostock quota exhausted while synthesizing market cap on %s", ts_code)
            market_cap_repo.upsert_many(rows)
            raise
        except Exception as exc:
            logger.warning("profit_data fetch failed for %s: %s", ts_code, exc)

        kline = kline_repo.get(ts_code, snapshot_date)
        close = kline.close_raw if kline else None
        total_share = profit.total_share if profit else None
        liqa_share = profit.liqa_share if profit else None

        if total_share is None or close is None:
            rows.append(
                MarketCapUpsertRow(
                    ts_code=ts_code,
                    market_cap_source=SOURCE_MISSING,
                    total_share=total_share,
                    liqa_share=liqa_share,
                    snapshot_close=close,
                    snapshot_date=snapshot_date,
                    snapshot_at=now,
                )
            )
            missing += 1
            continue

        total_cap = (total_share * close).quantize(Decimal("0.01"))
        circ_cap = (
            (liqa_share * close).quantize(Decimal("0.01")) if liqa_share is not None else None
        )
        rows.append(
            MarketCapUpsertRow(
                ts_code=ts_code,
                market_cap_source=SOURCE_SYNTH,
                total_market_cap=total_cap,
                circ_market_cap=circ_cap,
                total_share=total_share,
                liqa_share=liqa_share,
                snapshot_close=close,
                snapshot_date=snapshot_date,
                snapshot_at=now,
            )
        )
        synthesized += 1

    market_cap_repo.upsert_many(rows)
    return SyncMarketCapResult(total=len(ts_codes), synthesized=synthesized, missing=missing)
