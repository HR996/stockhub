"""Recoverable range-initialization behavior."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

import pytest

from app.core.errors import AdapterError, AdapterQuotaExceededError
from app.data_service.tushare_pipeline import (
    PipelineResult,
    TradeDateSyncStats,
    init_range_from_tushare,
)


@contextmanager
def _session_factory():
    yield object()


class _TaskRepo:
    rows: ClassVar[dict[tuple[str, str | None], SimpleNamespace]] = {}

    def __init__(self, session) -> None:
        _ = session

    def upsert_by_key(self, row) -> int:
        self.rows[(row.task_type, row.task_key)] = SimpleNamespace(**row.__dict__)
        return 1

    def find_by_key(self, task_type, task_key):
        return self.rows.get((task_type, task_key))


class _TradeCalRepo:
    def __init__(self, session) -> None:
        _ = session

    def list_range(self, start, end):
        _ = start, end
        return [
            SimpleNamespace(cal_date=date(2026, 5, 8), is_open=True),
            SimpleNamespace(cal_date=date(2026, 5, 11), is_open=True),
        ]


def _success(task_type: str) -> PipelineResult:
    return PipelineResult(task_type, task_type, "SUCCESS")


def test_init_resumes_committed_day_and_commits_remaining_day() -> None:
    _TaskRepo.rows = {
        ("TUSHARE_UPDATE_DAILY", "TUSHARE_UPDATE_DAILY:2026-05-08"):
            SimpleNamespace(status="SUCCESS")
    }
    stats = TradeDateSyncStats(
        trade_date=date(2026, 5, 11),
        daily_rows=10,
        daily_basic_rows=10,
        adj_factor_rows=10,
        kline_rows_written=10,
        market_cap_rows_written=10,
        adj_factor_rows_written=10,
    )
    with (
        patch("app.data_service.tushare_pipeline.TaskLogRepo", _TaskRepo),
        patch("app.data_service.tushare_pipeline.TradeCalRepo", _TradeCalRepo),
        patch(
            "app.data_service.tushare_pipeline.sync_stock_basic_from_tushare",
            return_value=_success("TUSHARE_SYNC_BASIC"),
        ),
        patch(
            "app.data_service.tushare_pipeline.sync_trade_calendar_from_tushare",
            return_value=_success("TUSHARE_SYNC_TRADE_CAL"),
        ),
        patch(
            "app.data_service.tushare_pipeline.sync_trade_date_from_tushare",
            return_value=stats,
        ) as daily,
        patch(
            "app.data_service.tushare_pipeline.rebuild_qfq_cache",
            return_value=(1, 2),
        ),
    ):
        result = init_range_from_tushare(
            object(),
            _session_factory,
            start=date(2026, 5, 8),
            end=date(2026, 5, 11),
            triggered_by="test",
        )

    assert daily.call_count == 1
    assert result.status == "SUCCESS"
    assert result.expected_count == 2
    assert result.success_count == 2
    assert result.error_summary["skipped_dates"] == 1


def test_init_continues_after_recoverable_adapter_error() -> None:
    _TaskRepo.rows = {}
    stats = TradeDateSyncStats(
        trade_date=date(2026, 5, 11), kline_rows_written=10
    )
    with (
        patch("app.data_service.tushare_pipeline.TaskLogRepo", _TaskRepo),
        patch("app.data_service.tushare_pipeline.TradeCalRepo", _TradeCalRepo),
        patch(
            "app.data_service.tushare_pipeline.sync_stock_basic_from_tushare",
            return_value=_success("TUSHARE_SYNC_BASIC"),
        ),
        patch(
            "app.data_service.tushare_pipeline.sync_trade_calendar_from_tushare",
            return_value=_success("TUSHARE_SYNC_TRADE_CAL"),
        ),
        patch(
            "app.data_service.tushare_pipeline.sync_trade_date_from_tushare",
            side_effect=[AdapterError("temporary"), stats],
        ),
        patch(
            "app.data_service.tushare_pipeline.rebuild_qfq_cache",
            return_value=(1, 2),
        ),
    ):
        result = init_range_from_tushare(
            object(),
            _session_factory,
            start=date(2026, 5, 8),
            end=date(2026, 5, 11),
            triggered_by="test",
        )

    assert result.status == "PARTIAL"
    assert result.success_count == 1
    assert result.error_count == 1


def test_init_stops_on_quota_error() -> None:
    _TaskRepo.rows = {}
    with (
        patch("app.data_service.tushare_pipeline.TaskLogRepo", _TaskRepo),
        patch("app.data_service.tushare_pipeline.TradeCalRepo", _TradeCalRepo),
        patch(
            "app.data_service.tushare_pipeline.sync_stock_basic_from_tushare",
            return_value=_success("TUSHARE_SYNC_BASIC"),
        ),
        patch(
            "app.data_service.tushare_pipeline.sync_trade_calendar_from_tushare",
            return_value=_success("TUSHARE_SYNC_TRADE_CAL"),
        ),
        patch(
            "app.data_service.tushare_pipeline.sync_trade_date_from_tushare",
            side_effect=AdapterQuotaExceededError("quota"),
        ),pytest.raises(AdapterQuotaExceededError)
    ):
        init_range_from_tushare(
            object(),
            _session_factory,
            start=date(2026, 5, 8),
            end=date(2026, 5, 11),
            triggered_by="test",
        )
