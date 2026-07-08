"""P1-06 — Integration tests for sync_kline_service (real baostock + real PG).

DoD: 20 stocks × 5+ trading days round-trip. Uses session-scoped `bs_session`
from tests/conftest.py (one baostock login per pytest process).

Idempotency test replays cached adapter output rather than doing a second real
fetch — see PROJECT.md §11.5 baostock quota rules.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.repositories.kline_repo import KLineRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.services.sync_kline_service import (
    STATUS_SUCCESS,
    TASK_KLINE,
    sync_kline_for_stocks,
)

pytestmark = pytest.mark.integration


# 20 stable large-caps sampled across SH main / SZ main / ChiNext / STAR.
SAMPLE_STOCKS = [
    "600000.SH", "600036.SH", "600519.SH", "600887.SH", "601398.SH",
    "601857.SH", "601988.SH", "600030.SH", "600028.SH", "601318.SH",
    "000001.SZ", "000333.SZ", "000651.SZ", "000858.SZ", "002415.SZ",
    "300059.SZ", "300750.SZ", "300760.SZ", "688981.SH", "688111.SH",
]


START = date(2024, 1, 2)
END = date(2024, 1, 12)  # 9 trading days in this window; test asserts >=5


def test_sync_kline_20_stocks_five_days(bs_session, db) -> None:
    kline_repo = KLineRepo(db)
    task_repo = TaskLogRepo(db)

    r = sync_kline_for_stocks(
        ts_codes=SAMPLE_STOCKS,
        start_date=START, end_date=END,
        kline_repo=kline_repo, task_repo=task_repo,
        triggered_by="test-p1-06", today=date(2026, 7, 7),
    )
    db.commit()

    assert r.status == STATUS_SUCCESS
    assert r.expected_count == 20
    assert r.success_count == 20
    assert r.error_count == 0
    assert r.missing_count == 0
    # 20 stocks × ~7 trading days in the window ≥ 100 rows
    assert r.rows_written >= 100
    assert kline_repo.count() == r.rows_written

    # Task log persisted
    latest = task_repo.latest_by_type(TASK_KLINE)
    assert latest is not None
    assert latest.status == STATUS_SUCCESS
    assert latest.expected_count == 20
    assert latest.success_count == 20


def test_sync_kline_stores_all_three_adjust_flags(bs_session, db) -> None:
    """One stock, one trading day: verify raw/qfq/hfq all populated with sensible prices."""
    kline_repo = KLineRepo(db)
    task_repo = TaskLogRepo(db)

    sync_kline_for_stocks(
        ts_codes=["600000.SH"],
        start_date=date(2024, 1, 2), end_date=date(2024, 1, 5),
        kline_repo=kline_repo, task_repo=task_repo,
        triggered_by="test", today=date(2026, 7, 7),
    )
    db.commit()

    row = kline_repo.get("600000.SH", date(2024, 1, 2))
    assert row is not None
    # All three flags should have real closing prices (浦发 in Jan 2024)
    assert row.close_raw is not None and row.close_raw > 0
    assert row.close_qfq is not None and row.close_qfq > 0
    assert row.close_hfq is not None and row.close_hfq > 0
    # In Jan 2024, hfq > raw > qfq is typical for a bank stock post-dividend history
    assert row.trade_status == 1
    assert row.volume is not None and row.volume > 0


def test_sync_kline_is_idempotent(bs_session, db) -> None:
    """Idempotency: first run hits baostock; second run replays cached rows."""
    from app.adapters.baostock_adapter import (
        ADJUST_HFQ,
        ADJUST_QFQ,
        ADJUST_RAW,
        fetch_kline,
    )

    kline_repo = KLineRepo(db)
    task_repo = TaskLogRepo(db)
    codes = ["600000.SH", "000001.SZ"]
    start, end = date(2024, 1, 2), date(2024, 1, 5)

    # Cache real responses once (2 stocks × 3 flags = 6 real calls total).
    cache: dict[tuple[str, str], list] = {}
    for ts in codes:
        num, market = ts.split(".", 1)
        bs_code = f"{market.lower()}.{num}"
        for flag in (ADJUST_RAW, ADJUST_QFQ, ADJUST_HFQ):
            cache[(bs_code, flag)] = fetch_kline(bs_code, start, end, flag)

    def replay(bs_code, s, e, flag):
        return cache[(bs_code, flag)]

    with patch("app.services.sync_kline_service.fetch_kline", side_effect=replay):
        sync_kline_for_stocks(
            ts_codes=codes,
            start_date=start, end_date=end,
            kline_repo=kline_repo, task_repo=task_repo,
            triggered_by="test", today=date(2026, 7, 7),
        )
        db.commit()
        n1 = kline_repo.count()
        task_count_1 = task_repo.count()

        # Same window, same day: no new rows should be added, no extra baostock calls.
        sync_kline_for_stocks(
            ts_codes=codes,
            start_date=start, end_date=end,
            kline_repo=kline_repo, task_repo=task_repo,
            triggered_by="test", today=date(2026, 7, 7),
        )
        db.commit()

    assert kline_repo.count() == n1
    # data_update_task should have exactly 1 row for this task_key
    assert task_repo.count() == task_count_1


def test_sync_kline_records_task_summary_fields(bs_session, db) -> None:
    kline_repo = KLineRepo(db)
    task_repo = TaskLogRepo(db)

    sync_kline_for_stocks(
        ts_codes=["600000.SH"],
        start_date=date(2024, 1, 2), end_date=date(2024, 1, 5),
        kline_repo=kline_repo, task_repo=task_repo,
        triggered_by="test", today=date(2026, 7, 7),
    )
    db.commit()

    latest = task_repo.latest_by_type(TASK_KLINE)
    assert latest is not None
    assert latest.expected_count == 1
    assert latest.success_count == 1
    assert latest.missing_count == 0
    assert latest.error_count == 0
