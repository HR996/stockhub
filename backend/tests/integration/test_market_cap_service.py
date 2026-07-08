"""P1-04 (redo) — Integration tests for market_cap_service full synthesis path.

Uses real DB (PG) + fake profit adapter + real KLineRepo populated via test fixture.
No baostock network access needed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.adapters.baostock_types import ProfitDataRow
from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.market_cap_repo import MarketCapRepo
from app.services.market_cap_service import (
    SOURCE_MISSING,
    SOURCE_SYNTH,
    synthesize_for,
)

pytestmark = pytest.mark.integration


SNAP = date(2024, 6, 28)


def _kline(ts_code: str, close: str) -> KLineRow:
    return KLineRow(
        ts_code=ts_code,
        trade_date=SNAP,
        trade_status=1,
        close_raw=Decimal(close),
        close_qfq=Decimal(close),
        close_hfq=Decimal(close),
    )


def _profit(bs_code: str, total_share: str, liqa_share: str) -> ProfitDataRow:
    return ProfitDataRow(
        bs_code=bs_code,
        pub_date=date(2024, 4, 30),
        stat_date=date(2024, 3, 31),
        total_share=Decimal(total_share),
        liqa_share=Decimal(liqa_share),
    )


def test_synthesize_writes_market_cap_when_both_sides_present(db) -> None:
    kline_repo = KLineRepo(db)
    kline_repo.upsert_many([
        _kline("600000.SH", "10.00"),
        _kline("000001.SZ", "12.50"),
    ])
    db.commit()
    mc_repo = MarketCapRepo(db)

    def fake_profit(bs_code: str, year: int, quarter: int):
        table = {
            "sh.600000": _profit("sh.600000", "29352178996", "29352178996"),
            "sz.000001": _profit("sz.000001", "19405918198", "19405918198"),
        }
        return table.get(bs_code)

    with patch("app.services.market_cap_service.fetch_profit_data", side_effect=fake_profit):
        result = synthesize_for(
            ts_codes=["600000.SH", "000001.SZ"],
            snapshot_date=SNAP,
            kline_repo=kline_repo,
            market_cap_repo=mc_repo,
        )
        db.commit()

    assert result.total == 2
    assert result.synthesized == 2
    assert result.missing == 0

    row = mc_repo.get_by_ts_code("600000.SH")
    assert row is not None
    assert row.market_cap_source == SOURCE_SYNTH
    assert row.total_share == Decimal("29352178996.00")
    assert row.snapshot_close == Decimal("10.0000")
    assert row.total_market_cap == Decimal("293521789960.00")


def test_synthesize_marks_missing_when_profit_absent(db) -> None:
    kline_repo = KLineRepo(db)
    kline_repo.upsert_many([_kline("430047.BJ", "8.00")])
    db.commit()
    mc_repo = MarketCapRepo(db)

    with patch("app.services.market_cap_service.fetch_profit_data", return_value=None):
        result = synthesize_for(
            ts_codes=["430047.BJ"],
            snapshot_date=SNAP,
            kline_repo=kline_repo,
            market_cap_repo=mc_repo,
        )
        db.commit()

    assert result.synthesized == 0
    assert result.missing == 1

    row = mc_repo.get_by_ts_code("430047.BJ")
    assert row is not None
    assert row.market_cap_source == SOURCE_MISSING
    assert row.total_market_cap is None
    assert row.total_share is None
    assert row.snapshot_close == Decimal("8.0000")   # kline present, still recorded


def test_synthesize_marks_missing_when_kline_absent(db) -> None:
    kline_repo = KLineRepo(db)
    mc_repo = MarketCapRepo(db)

    def fake_profit(bs_code: str, year: int, quarter: int):
        return _profit(bs_code, "1000000000", "1000000000")

    with patch("app.services.market_cap_service.fetch_profit_data", side_effect=fake_profit):
        result = synthesize_for(
            ts_codes=["600000.SH"],
            snapshot_date=SNAP,
            kline_repo=kline_repo,
            market_cap_repo=mc_repo,
        )
        db.commit()

    assert result.synthesized == 0
    assert result.missing == 1
    row = mc_repo.get_by_ts_code("600000.SH")
    assert row is not None
    assert row.market_cap_source == SOURCE_MISSING
    assert row.total_share == Decimal("1000000000.00")
    assert row.total_market_cap is None
    assert row.snapshot_close is None


def test_synthesize_is_idempotent(db) -> None:
    kline_repo = KLineRepo(db)
    kline_repo.upsert_many([_kline("600000.SH", "10.00")])
    db.commit()
    mc_repo = MarketCapRepo(db)

    def fake_profit(*a, **kw):
        return _profit("sh.600000", "29352178996", "29352178996")

    with patch("app.services.market_cap_service.fetch_profit_data", side_effect=fake_profit):
        synthesize_for(["600000.SH"], SNAP, kline_repo, mc_repo)
        db.commit()
        synthesize_for(["600000.SH"], SNAP, kline_repo, mc_repo)
        db.commit()

    assert mc_repo.count() == 1


def test_synthesize_swallows_adapter_error_and_marks_missing(db) -> None:
    """Adapter exceptions are logged and treated as missing — doesn't abort the batch."""
    kline_repo = KLineRepo(db)
    kline_repo.upsert_many([_kline("600000.SH", "10.00")])
    db.commit()
    mc_repo = MarketCapRepo(db)

    def broken(*a, **kw):
        raise ConnectionError("baostock unreachable")

    with patch("app.services.market_cap_service.fetch_profit_data", side_effect=broken):
        result = synthesize_for(["600000.SH"], SNAP, kline_repo, mc_repo)
        db.commit()

    assert result.synthesized == 0
    assert result.missing == 1
    row = mc_repo.get_by_ts_code("600000.SH")
    assert row is not None
    assert row.market_cap_source == SOURCE_MISSING
