"""P1-05 — Integration tests for sync_basic_service (real baostock + real PG).

Uses:
- session-scoped `bs_session` fixture from tests/conftest.py (one baostock login per
  pytest process, avoids `10001011 黑名单用户` blacklist)
- test-scoped `db` from tests/conftest.py

Full-market sync is expensive (~5000 stocks); one such run is enough to prove
the happy path. Idempotency is verified WITHOUT a second real fetch — the second
call is patched to return the first call's cached rows, so we only spend the
baostock quota once per pytest run (see PROJECT.md §11.5).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.repositories.stock_repo import StockBasicRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.repositories.trade_cal_repo import TradeCalRepo
from app.services.sync_basic_service import (
    STATUS_SUCCESS,
    TASK_STOCK_BASIC,
    TASK_TRADE_CAL,
    sync_stock_basic,
    sync_trade_calendar,
)

pytestmark = pytest.mark.integration


def test_sync_stock_basic_full_market(bs_session, db) -> None:
    stock_repo = StockBasicRepo(db)
    task_repo = TaskLogRepo(db)

    result = sync_stock_basic(
        stock_repo=stock_repo, task_repo=task_repo,
        triggered_by="test-p1-05", today=date(2026, 7, 7),
    )
    db.commit()

    assert result.status == STATUS_SUCCESS
    # Full A-share market > 4000 tickers (stocks + funds + indexes appear in query_stock_basic)
    assert result.expected_count > 4000
    assert result.success_count == result.expected_count
    assert stock_repo.count() == result.success_count

    # Task log has one row for today with SUCCESS
    latest = task_repo.latest_by_type(TASK_STOCK_BASIC)
    assert latest is not None
    assert latest.status == STATUS_SUCCESS
    assert latest.task_key == "SYNC_STOCK_BASIC:2026-07-07"
    assert latest.success_count == result.success_count


def test_sync_stock_basic_idempotent(bs_session, db) -> None:
    """Idempotency: first run hits baostock; second run reuses cached rows via patch.

    Rationale: verifying idempotency does not require a second full-market real
    fetch (~4000 records). We cache the first response and replay it — the DB
    upsert path is what we're testing, not the network path.
    """
    from app.adapters.baostock_adapter import fetch_stock_basic as real_fetch

    stock_repo = StockBasicRepo(db)
    task_repo = TaskLogRepo(db)

    cached_rows = real_fetch()
    with patch(
        "app.services.sync_basic_service.fetch_stock_basic",
        return_value=cached_rows,
    ):
        sync_stock_basic(stock_repo, task_repo, triggered_by="test", today=date(2026, 7, 7))
        db.commit()
        n1 = stock_repo.count()

        sync_stock_basic(stock_repo, task_repo, triggered_by="test", today=date(2026, 7, 7))
        db.commit()
        n2 = stock_repo.count()

    assert n1 == n2  # no duplicates
    # data_update_task should only have 1 row for this task_type + task_key
    assert task_repo.count() == 1


def test_sync_trade_calendar_narrow_range(bs_session, db) -> None:
    trade_repo = TradeCalRepo(db)
    task_repo = TaskLogRepo(db)

    result = sync_trade_calendar(
        trade_cal_repo=trade_repo, task_repo=task_repo,
        triggered_by="test", today=date(2026, 7, 7),
        start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
    )
    db.commit()

    assert result.status == STATUS_SUCCESS
    assert result.success_count == 31
    assert trade_repo.count() == 31
    latest = task_repo.latest_by_type(TASK_TRADE_CAL)
    assert latest is not None
    assert latest.status == STATUS_SUCCESS
    assert latest.expected_count == 31
    assert latest.success_count == 31


def test_sync_trade_calendar_idempotent(bs_session, db) -> None:
    """Idempotency: first real fetch is cached and replayed for the second run."""
    from app.adapters.baostock_adapter import fetch_trade_cal as real_fetch

    trade_repo = TradeCalRepo(db)
    task_repo = TaskLogRepo(db)

    start, end = date(2024, 1, 1), date(2024, 1, 15)
    cached_rows = real_fetch(start, end)
    with patch(
        "app.services.sync_basic_service.fetch_trade_cal",
        return_value=cached_rows,
    ):
        sync_trade_calendar(
            trade_repo, task_repo, triggered_by="test", today=date(2026, 7, 7),
            start_date=start, end_date=end,
        )
        db.commit()
        n1 = trade_repo.count()

        sync_trade_calendar(
            trade_repo, task_repo, triggered_by="test", today=date(2026, 7, 7),
            start_date=start, end_date=end,
        )
        db.commit()
        n2 = trade_repo.count()

    assert n1 == n2 == 15
    assert task_repo.count() == 1
