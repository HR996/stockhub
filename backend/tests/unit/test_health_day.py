"""P2-02 — Unit tests for health_day_service (fake repos, no DB)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import date as date_cls
from typing import Any

import pytest

from app.core.errors import NotFoundError
from app.services.health_day_service import (
    MAX_LISTED_CODES,
    TASK_KLINE,
    get_day_detail,
)


class _FakeTradeCalRepo:
    def __init__(self, trading_days: set[date_cls]) -> None:
        self._days = trading_days

    def is_trading_day(self, day: date_cls) -> bool:
        return day in self._days


class _FakeStockRepo:
    def __init__(self, active_by_day: dict[date_cls, list[str]]) -> None:
        self._map = active_by_day

    def list_active_ts_codes_at(self, day: date_cls) -> list[str]:
        return list(self._map.get(day, []))


class _FakeKLineRepo:
    def __init__(
        self,
        actual_by_day: dict[date_cls, set[str]] | None = None,
        anomaly_by_day: dict[date_cls, set[str]] | None = None,
    ) -> None:
        self._actual = actual_by_day or {}
        self._anomaly = anomaly_by_day or {}

    def ts_codes_on(self, day: date_cls) -> set[str]:
        return set(self._actual.get(day, set()))

    def anomaly_ts_codes_on(self, day: date_cls) -> set[str]:
        return set(self._anomaly.get(day, set()))


@dataclass
class _FakeTaskRow:
    task_key: str | None
    status: str
    finished_at: datetime | None = None
    error_summary: dict[str, Any] | None = None


class _FakeTaskRepo:
    def __init__(self, latest: _FakeTaskRow | None = None) -> None:
        self._latest = latest

    def latest_by_type(self, task_type: str):
        return self._latest if task_type == TASK_KLINE else None


D = date_cls(2024, 1, 2)   # a trading day in our fakes
D_NON = date_cls(2024, 1, 6)  # Saturday — never in trading_days


def test_non_trading_day_raises_not_found() -> None:
    """US-3.3 侧线：非交易日 → NOT_FOUND_TRADING_DAY。"""
    with pytest.raises(NotFoundError, match="2024-01-06"):
        get_day_detail(
            D_NON,
            trade_cal_repo=_FakeTradeCalRepo({D}),
            stock_repo=_FakeStockRepo({}),
            kline_repo=_FakeKLineRepo(),
            task_repo=_FakeTaskRepo(),
        )


def test_full_success_no_missing_no_error() -> None:
    codes = [f"60000{i}.SH" for i in range(5)]
    r = get_day_detail(
        D,
        trade_cal_repo=_FakeTradeCalRepo({D}),
        stock_repo=_FakeStockRepo({D: codes}),
        kline_repo=_FakeKLineRepo({D: set(codes)}),
        task_repo=_FakeTaskRepo(),
    )
    assert r.expected_count == 5
    assert r.success_count == 5
    assert r.missing_count == 0
    assert r.error_count == 0
    assert r.missing_ts_codes == []
    assert r.error_ts_codes == []


def test_missing_and_error_are_reported() -> None:
    """US-3.3 EARS #2: expected/success/missing/error 全部有值，异常摘要列出 ts_code。"""
    active = ["600000.SH", "600001.SH", "600002.SH", "600003.SH"]
    fetched = {"600000.SH", "600001.SH", "600002.SH"}          # 600003 missing
    anomaly = {"600002.SH"}                                     # 600002 is anomalous
    r = get_day_detail(
        D,
        trade_cal_repo=_FakeTradeCalRepo({D}),
        stock_repo=_FakeStockRepo({D: active}),
        kline_repo=_FakeKLineRepo({D: fetched}, {D: anomaly}),
        task_repo=_FakeTaskRepo(),
    )
    assert r.expected_count == 4
    assert r.success_count == 2         # 3 fetched - 1 anomalous
    assert r.missing_count == 1
    assert r.error_count == 1
    assert r.missing_ts_codes == ["600003.SH"]
    assert r.error_ts_codes == ["600002.SH"]


def test_anomaly_only_counted_if_row_exists() -> None:
    """A code with no kline row is 'missing', not 'error' — even if listed as anomalous somehow."""
    active = ["A.SH", "B.SH"]
    fetched: set[str] = set()  # nothing fetched
    anomaly = {"A.SH"}          # stale flag; should be ignored since no row
    r = get_day_detail(
        D,
        trade_cal_repo=_FakeTradeCalRepo({D}),
        stock_repo=_FakeStockRepo({D: active}),
        kline_repo=_FakeKLineRepo({D: fetched}, {D: anomaly}),
        task_repo=_FakeTaskRepo(),
    )
    assert r.missing_count == 2
    assert r.error_count == 0


def test_missing_and_error_lists_are_capped() -> None:
    active = [f"A{i:04d}.SH" for i in range(200)]
    fetched: set[str] = set()
    r = get_day_detail(
        D,
        trade_cal_repo=_FakeTradeCalRepo({D}),
        stock_repo=_FakeStockRepo({D: active}),
        kline_repo=_FakeKLineRepo({D: fetched}),
        task_repo=_FakeTaskRepo(),
    )
    assert r.missing_count == 200
    assert len(r.missing_ts_codes) == MAX_LISTED_CODES


def test_latest_task_included_when_key_covers_day() -> None:
    fetched = {"600000.SH"}
    task = _FakeTaskRow(
        task_key="SYNC_KLINE:2026-07-07:2024-01-01:2024-01-05",
        status="SUCCESS",
        finished_at=datetime(2026, 7, 7, 3, 30, tzinfo=UTC),
        error_summary={"errors": []},
    )
    r = get_day_detail(
        D,
        trade_cal_repo=_FakeTradeCalRepo({D}),
        stock_repo=_FakeStockRepo({D: ["600000.SH"]}),
        kline_repo=_FakeKLineRepo({D: fetched}),
        task_repo=_FakeTaskRepo(task),
    )
    assert r.latest_task_status == "SUCCESS"
    assert r.latest_task_finished_at is not None
    assert r.latest_task_error_summary == {"errors": []}


def test_latest_task_dropped_when_window_does_not_cover_day() -> None:
    task = _FakeTaskRow(
        task_key="SYNC_KLINE:2026-07-07:2024-02-01:2024-02-28",  # window doesn't cover D
        status="SUCCESS",
    )
    r = get_day_detail(
        D,
        trade_cal_repo=_FakeTradeCalRepo({D}),
        stock_repo=_FakeStockRepo({D: ["600000.SH"]}),
        kline_repo=_FakeKLineRepo({D: {"600000.SH"}}),
        task_repo=_FakeTaskRepo(task),
    )
    assert r.latest_task_status is None


def test_latest_task_malformed_key_ignored() -> None:
    task = _FakeTaskRow(task_key="SYNC_KLINE:garbage", status="FAILED")
    r = get_day_detail(
        D,
        trade_cal_repo=_FakeTradeCalRepo({D}),
        stock_repo=_FakeStockRepo({D: []}),
        kline_repo=_FakeKLineRepo(),
        task_repo=_FakeTaskRepo(task),
    )
    assert r.latest_task_status is None
