"""P1-06 — Unit tests for sync_kline_service (mocked adapter)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app.adapters.baostock_types import KLinePriceGroup
from app.core.errors import AdapterQuotaExceededError
from app.services.sync_kline_service import (
    STATUS_FAILED,
    STATUS_PARTIAL,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    TASK_KLINE,
    _bs_code_from_ts,
    _merge_one_stock,
    sync_kline_for_stocks,
)


def _pg(ts: str, d: date, close, status: int = 1) -> KLinePriceGroup:
    return KLinePriceGroup(
        ts_code=ts, trade_date=d,
        open=None, high=None, low=None,
        close=Decimal(close) if close is not None else None,
        preclose=None,
        volume=Decimal("1000") if close else None,
        amount=Decimal("1000") if close else None,
        turn=None, pct_chg=None,
        trade_status=status, is_st=False,
    )


class _FakeKLineRepo:
    def __init__(self) -> None:
        self.rows: list = []

    def upsert_many(self, rows) -> int:
        rows = list(rows)
        self.rows.extend(rows)
        return len(rows)


class _FakeTaskRepo:
    def __init__(self) -> None:
        self.calls = []

    def upsert_by_key(self, row) -> int:
        self.calls.append(row)
        return len(self.calls)

    def statuses(self) -> list[str]:
        return [c.status for c in self.calls]


D = date(2024, 1, 2)
D2 = date(2024, 1, 3)


def test_bs_code_from_ts_maps_all_markets() -> None:
    assert _bs_code_from_ts("600000.SH") == "sh.600000"
    assert _bs_code_from_ts("000001.SZ") == "sz.000001"
    assert _bs_code_from_ts("430047.BJ") == "bj.430047"


def test_merge_uses_all_dates_and_null_missing_prices() -> None:
    raw = [_pg("600000.SH", D, "10.00")]
    qfq = [_pg("600000.SH", D, "9.50"), _pg("600000.SH", D2, "9.60")]
    hfq: list[KLinePriceGroup] = []

    merged = _merge_one_stock(raw, qfq, hfq)
    assert [r.trade_date for r in merged] == [D, D2]

    r0 = merged[0]
    assert r0.close_raw == Decimal("10.00")
    assert r0.close_qfq == Decimal("9.50")
    assert r0.close_hfq is None
    r1 = merged[1]
    assert r1.close_raw is None
    assert r1.close_qfq == Decimal("9.60")
    assert r1.close_hfq is None


def test_merge_preserves_suspended_day() -> None:
    """Suspended day: prices None everywhere, trade_status=0 preserved."""
    raw = [_pg("600000.SH", D, close=None, status=0)]
    merged = _merge_one_stock(raw, [], [])
    assert len(merged) == 1
    assert merged[0].trade_status == 0
    assert merged[0].close_raw is None


def test_sync_kline_full_success() -> None:
    kline_repo = _FakeKLineRepo()
    task_repo = _FakeTaskRepo()

    def fake_fetch(bs_code, start, end, adjustflag):
        return [_pg("600000.SH", D, "10.00" if adjustflag == "3" else "9.50")]

    with patch("app.services.sync_kline_service.fetch_kline", side_effect=fake_fetch):
        r = sync_kline_for_stocks(
            ts_codes=["600000.SH"],
            start_date=D, end_date=D,
            kline_repo=kline_repo, task_repo=task_repo,
            triggered_by="t", today=date(2026, 7, 7),
        )

    assert r.status == STATUS_SUCCESS
    assert r.expected_count == 1
    assert r.success_count == 1
    assert r.error_count == 0
    assert r.missing_count == 0
    assert r.rows_written == 1
    assert task_repo.statuses() == [STATUS_RUNNING, STATUS_SUCCESS]
    assert task_repo.calls[-1].task_key == f"{TASK_KLINE}:2026-07-07:2024-01-02:2024-01-02"


def test_sync_kline_partial_when_some_stocks_error() -> None:
    kline_repo = _FakeKLineRepo()
    task_repo = _FakeTaskRepo()

    def fake_fetch(bs_code, start, end, adjustflag):
        if bs_code == "sh.600002":
            raise ConnectionError("baostock hiccup")
        return [_pg(f"{bs_code.split('.')[1]}.SH", D, "10.00")]

    with patch("app.services.sync_kline_service.fetch_kline", side_effect=fake_fetch):
        r = sync_kline_for_stocks(
            ts_codes=["600000.SH", "600001.SH", "600002.SH"],
            start_date=D, end_date=D,
            kline_repo=kline_repo, task_repo=task_repo,
            triggered_by="t", today=date(2026, 7, 7),
        )

    assert r.status == STATUS_PARTIAL
    assert r.success_count == 2
    assert r.error_count == 1
    assert r.rows_written == 2
    assert task_repo.calls[-1].error_summary["errors"] == ["600002.SH"]


def test_sync_kline_missing_when_all_flags_empty() -> None:
    kline_repo = _FakeKLineRepo()
    task_repo = _FakeTaskRepo()

    with patch("app.services.sync_kline_service.fetch_kline", return_value=[]):
        r = sync_kline_for_stocks(
            ts_codes=["600000.SH"],
            start_date=D, end_date=D,
            kline_repo=kline_repo, task_repo=task_repo,
            triggered_by="t", today=date(2026, 7, 7),
        )

    assert r.status == STATUS_PARTIAL
    assert r.missing_count == 1
    assert r.success_count == 0
    assert r.rows_written == 0


def test_sync_kline_all_fail_becomes_failed() -> None:
    kline_repo = _FakeKLineRepo()
    task_repo = _FakeTaskRepo()

    with patch(
        "app.services.sync_kline_service.fetch_kline",
        side_effect=ConnectionError("boom"),
    ):
        r = sync_kline_for_stocks(
            ts_codes=["600000.SH", "000001.SZ"],
            start_date=D, end_date=D,
            kline_repo=kline_repo, task_repo=task_repo,
            triggered_by="t", today=date(2026, 7, 7),
        )

    assert r.status == STATUS_FAILED
    assert r.error_count == 2
    assert r.success_count == 0
    assert r.rows_written == 0


def test_sync_kline_quota_exhausted_aborts_batch() -> None:
    """AdapterQuotaExceededError 立即中止 loop，剩余股票不再消耗预算。"""
    kline_repo = _FakeKLineRepo()
    task_repo = _FakeTaskRepo()
    seen_codes: list[str] = []

    def fake_fetch(bs_code, start, end, adjustflag):
        seen_codes.append(bs_code)
        if bs_code == "sh.600001":
            raise AdapterQuotaExceededError("baostock quota exceeded: 10001007")
        return [_pg("XXX.SH", D, "10.00")]

    with patch("app.services.sync_kline_service.fetch_kline", side_effect=fake_fetch):
        r = sync_kline_for_stocks(
            ts_codes=["600000.SH", "600001.SH", "600002.SH"],
            start_date=D, end_date=D,
            kline_repo=kline_repo, task_repo=task_repo,
            triggered_by="t", today=date(2026, 7, 7),
        )

    # First stock consumed all 3 fetches; second stock hits quota on first fetch;
    # third stock must NOT be tried (batch aborted).
    assert "sh.600002" not in seen_codes
    assert r.status == STATUS_FAILED
    assert task_repo.calls[-1].error_summary.get("quota_exhausted") is True
