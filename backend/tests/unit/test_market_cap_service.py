"""P1-04 (redo) — Unit tests for market_cap_service pure logic."""

from __future__ import annotations

from datetime import date

from app.services.market_cap_service import _bs_code_from_ts, _quarter_of


def test_bs_code_from_ts_all_markets() -> None:
    assert _bs_code_from_ts("600000.SH") == "sh.600000"
    assert _bs_code_from_ts("000001.SZ") == "sz.000001"
    assert _bs_code_from_ts("430047.BJ") == "bj.430047"


def test_quarter_of_previous_quarter_reduces_publish_lag() -> None:
    # Snapshot in July 2025 → previous quarter is 2025 Q2 (published in Jul-Aug)
    assert _quarter_of(date(2025, 7, 15)) == (2025, 2)
    # Snapshot in April 2025 → previous quarter is 2025 Q1
    assert _quarter_of(date(2025, 4, 30)) == (2025, 1)
    # Snapshot in January 2025 → previous quarter wraps to 2024 Q4
    assert _quarter_of(date(2025, 1, 5)) == (2024, 4)
    # Snapshot on the boundary Q1/Q2
    assert _quarter_of(date(2025, 3, 31)) == (2024, 4)
    assert _quarter_of(date(2025, 4, 1)) == (2025, 1)
