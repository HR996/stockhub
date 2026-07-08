"""P1-04 — MarketCapRepo idempotency."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.repositories.market_cap_repo import MarketCapRepo, MarketCapUpsertRow

pytestmark = pytest.mark.integration


def test_market_cap_upsert_is_idempotent(db) -> None:
    repo = MarketCapRepo(db)
    rows = [
        MarketCapUpsertRow(
            ts_code="600000.SH",
            market_cap_source="baostock_synth",
            total_market_cap=Decimal("350000000000.00"),
            circ_market_cap=Decimal("350000000000.00"),
        ),
        MarketCapUpsertRow(
            ts_code="000001.SZ",
            market_cap_source="baostock_synth",
            total_market_cap=Decimal("240000000000.00"),
            circ_market_cap=Decimal("240000000000.00"),
        ),
    ]
    assert repo.upsert_many(rows) == 2
    db.commit()
    assert repo.count() == 2

    # Re-run same rows
    repo.upsert_many(rows)
    db.commit()
    assert repo.count() == 2


def test_market_cap_upsert_updates_values(db) -> None:
    repo = MarketCapRepo(db)
    repo.upsert_many([
        MarketCapUpsertRow(
            ts_code="600000.SH",
            market_cap_source="baostock_synth",
            total_market_cap=Decimal("100.00"),
        )
    ])
    db.commit()

    repo.upsert_many([
        MarketCapUpsertRow(
            ts_code="600000.SH",
            market_cap_source="baostock_synth",
            total_market_cap=Decimal("200.00"),
        )
    ])
    db.commit()

    row = repo.get_by_ts_code("600000.SH")
    assert row is not None
    assert row.total_market_cap == Decimal("200.00")


def test_market_cap_missing_flag(db) -> None:
    """When source has no cap for a stock, source='baostock_missing' + null value."""
    repo = MarketCapRepo(db)
    repo.upsert_many([
        MarketCapUpsertRow(ts_code="600000.SH", market_cap_source="baostock_missing"),
        MarketCapUpsertRow(
            ts_code="000001.SZ",
            market_cap_source="baostock_synth",
            total_market_cap=Decimal("1000"),
        ),
    ])
    db.commit()

    assert repo.count() == 2
    assert repo.count_missing() == 1
    missing_row = repo.get_by_ts_code("600000.SH")
    assert missing_row is not None
    assert missing_row.total_market_cap is None
    assert missing_row.market_cap_source == "baostock_missing"
