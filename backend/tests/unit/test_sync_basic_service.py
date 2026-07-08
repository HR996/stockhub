"""P1-05 — Unit tests for sync_basic_service (mocked adapter, real DB not needed).

Uses simple in-memory fake repos to isolate service logic from SQL/network.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from app.adapters.baostock_types import (
    StockBasicRow as AdapterStockBasicRow,
)
from app.adapters.baostock_types import (
    TradeCalRow as AdapterTradeCalRow,
)
from app.services.sync_basic_service import (
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    TASK_STOCK_BASIC,
    TASK_TRADE_CAL,
    _default_calendar_range,
    sync_stock_basic,
    sync_trade_calendar,
)


class _FakeStockRepo:
    def __init__(self) -> None:
        self.batches: list[list] = []

    def upsert_many(self, rows) -> int:
        rows = list(rows)
        self.batches.append(rows)
        return len(rows)


class _FakeTradeCalRepo:
    def __init__(self) -> None:
        self.batches: list[list] = []

    def upsert_many(self, rows) -> int:
        rows = list(rows)
        self.batches.append(rows)
        return len(rows)


class _FakeTaskRepo:
    """Records every upsert_by_key call so tests can assert the RUNNING → SUCCESS/FAILED sequence."""

    def __init__(self) -> None:
        self.calls: list = []
        self._id = 0

    def upsert_by_key(self, row) -> int:
        self._id += 1
        self.calls.append(row)
        return self._id

    def statuses(self) -> list[str]:
        return [c.status for c in self.calls]


# ---------- helpers ----------

def _adapter_stock(ts: str, name: str = "浦发银行") -> AdapterStockBasicRow:
    return AdapterStockBasicRow(
        ts_code=ts, bs_code=f"{ts.split('.')[1].lower()}.{ts.split('.')[0]}",
        name=name, market=ts.split(".")[1],
        list_date=date(1999, 11, 10), delist_date=None,
        is_bj=ts.endswith(".BJ"), is_common=True,
    )


# ---------- default calendar range ----------

def test_default_calendar_range_covers_prev_3y_and_next_year() -> None:
    start, end = _default_calendar_range(date(2026, 7, 7))
    assert start == date(2023, 1, 1)
    assert end == date(2027, 12, 31)


# ---------- sync_stock_basic ----------

def test_sync_stock_basic_success_path() -> None:
    stock_repo = _FakeStockRepo()
    task_repo = _FakeTaskRepo()

    fake_rows = [_adapter_stock("600000.SH"), _adapter_stock("000001.SZ", "平安银行")]
    with patch(
        "app.services.sync_basic_service.fetch_stock_basic", return_value=fake_rows
    ):
        result = sync_stock_basic(
            stock_repo=stock_repo, task_repo=task_repo,
            triggered_by="test", today=date(2026, 7, 7),
        )

    assert result.status == STATUS_SUCCESS
    assert result.task_type == TASK_STOCK_BASIC
    assert result.task_key == "SYNC_STOCK_BASIC:2026-07-07"
    assert result.expected_count == 2
    assert result.success_count == 2
    assert task_repo.statuses() == [STATUS_RUNNING, STATUS_SUCCESS]
    assert len(stock_repo.batches) == 1
    assert len(stock_repo.batches[0]) == 2


def test_sync_stock_basic_marks_st_from_name() -> None:
    stock_repo = _FakeStockRepo()
    task_repo = _FakeTaskRepo()

    with patch(
        "app.services.sync_basic_service.fetch_stock_basic",
        return_value=[_adapter_stock("600001.SH", "*ST 天马"), _adapter_stock("600002.SH", "普通股")],
    ):
        sync_stock_basic(
            stock_repo=stock_repo, task_repo=task_repo,
            triggered_by="test", today=date(2026, 7, 7),
        )

    written = stock_repo.batches[0]
    st_row = next(r for r in written if r.ts_code == "600001.SH")
    normal_row = next(r for r in written if r.ts_code == "600002.SH")
    assert st_row.is_st is True
    assert normal_row.is_st is False


def test_sync_stock_basic_failure_records_task_log() -> None:
    stock_repo = _FakeStockRepo()
    task_repo = _FakeTaskRepo()

    with patch(
        "app.services.sync_basic_service.fetch_stock_basic",
        side_effect=ConnectionError("baostock unreachable"),
    ):
        result = sync_stock_basic(
            stock_repo=stock_repo, task_repo=task_repo,
            triggered_by="test", today=date(2026, 7, 7),
        )

    assert result.status == STATUS_FAILED
    assert result.error_message == "baostock unreachable"
    assert task_repo.statuses() == [STATUS_RUNNING, STATUS_FAILED]
    # No repo writes on failure
    assert stock_repo.batches == []


# ---------- sync_trade_calendar ----------

def test_sync_trade_calendar_success_uses_default_range() -> None:
    trade_repo = _FakeTradeCalRepo()
    task_repo = _FakeTaskRepo()

    fake_rows = [
        AdapterTradeCalRow(cal_date=date(2023, 1, 1) + timedelta(days=i),
                           is_open=(i % 7 not in (5, 6)))
        for i in range(3)
    ]
    with patch(
        "app.services.sync_basic_service.fetch_trade_cal", return_value=fake_rows
    ):
        result = sync_trade_calendar(
            trade_cal_repo=trade_repo, task_repo=task_repo,
            triggered_by="scheduler", today=date(2026, 7, 7),
        )

    assert result.status == STATUS_SUCCESS
    assert result.task_type == TASK_TRADE_CAL
    assert result.task_key == "SYNC_TRADE_CAL:2026-07-07"
    # Expected = default range (3+ full years, so > 1000 days); success = actual returned
    assert result.expected_count > 1000
    assert result.success_count == 3
    assert task_repo.statuses() == [STATUS_RUNNING, STATUS_SUCCESS]


def test_sync_trade_calendar_accepts_explicit_range() -> None:
    trade_repo = _FakeTradeCalRepo()
    task_repo = _FakeTaskRepo()

    with patch(
        "app.services.sync_basic_service.fetch_trade_cal", return_value=[]
    ) as fake_fetch:
        sync_trade_calendar(
            trade_cal_repo=trade_repo, task_repo=task_repo,
            triggered_by="test",
            today=date(2026, 7, 7),
            start_date=date(2024, 1, 1), end_date=date(2024, 1, 31),
        )

    fake_fetch.assert_called_once_with(date(2024, 1, 1), date(2024, 1, 31))


def test_sync_trade_calendar_failure_records_task_log() -> None:
    trade_repo = _FakeTradeCalRepo()
    task_repo = _FakeTaskRepo()

    with patch(
        "app.services.sync_basic_service.fetch_trade_cal",
        side_effect=RuntimeError("adapter boom"),
    ):
        result = sync_trade_calendar(
            trade_cal_repo=trade_repo, task_repo=task_repo,
            triggered_by="test", today=date(2026, 7, 7),
        )

    assert result.status == STATUS_FAILED
    assert task_repo.statuses() == [STATUS_RUNNING, STATUS_FAILED]
    assert trade_repo.batches == []


def test_double_run_uses_same_task_key() -> None:
    """Second call same day → same task_key → task repo receives 4 upserts (2×RUNNING+SUCCESS)."""
    stock_repo = _FakeStockRepo()
    task_repo = _FakeTaskRepo()

    with patch(
        "app.services.sync_basic_service.fetch_stock_basic",
        return_value=[_adapter_stock("600000.SH")],
    ):
        r1 = sync_stock_basic(stock_repo, task_repo, triggered_by="t", today=date(2026, 7, 7))
        r2 = sync_stock_basic(stock_repo, task_repo, triggered_by="t", today=date(2026, 7, 7))

    assert r1.task_key == r2.task_key == "SYNC_STOCK_BASIC:2026-07-07"
    # 4 = 2 runs × (RUNNING + SUCCESS)
    assert task_repo.statuses() == [STATUS_RUNNING, STATUS_SUCCESS, STATUS_RUNNING, STATUS_SUCCESS]
