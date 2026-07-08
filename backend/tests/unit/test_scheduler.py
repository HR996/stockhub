"""Unit tests for Tushare-backed scheduler orchestration."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

from app.core.errors import AdapterQuotaExceededError
from app.services.scheduler import DailySyncReport, build_scheduler, run_daily_sync


class _FakeSessionCtx:
    def __init__(self, session: object) -> None:
        self._session = session

    def __enter__(self) -> object:
        return self._session

    def __exit__(self, *a: object) -> bool:
        return False


def _make_session_factory(session: object):
    @contextmanager
    def _factory():
        yield session

    return _factory


class _FakeTradeRepo:
    def __init__(self, is_trading: bool) -> None:
        self._is = is_trading

    def is_trading_day(self, day: date) -> bool:
        return self._is


TODAY = date(2026, 7, 7)


def _patches_all_success(is_trading: bool = True) -> list[object]:
    r_basic = MagicMock(status="SUCCESS")
    r_cal = MagicMock(status="SUCCESS")
    r_daily = MagicMock(status="SUCCESS")

    return [
        patch("app.services.scheduler.tushare_session", return_value=_FakeSessionCtx(MagicMock())),
        patch("app.services.scheduler.TradeCalRepo", return_value=_FakeTradeRepo(is_trading)),
        patch("app.services.scheduler.sync_stock_basic_from_tushare", return_value=r_basic),
        patch("app.services.scheduler.sync_trade_calendar_from_tushare", return_value=r_cal),
        patch("app.services.scheduler.update_one_day_from_tushare", return_value=r_daily),
    ]


def _apply(patches: list[object]) -> None:
    for p in patches:
        p.__enter__()


def _tear(patches: list[object]) -> None:
    for p in reversed(patches):
        p.__exit__(None, None, None)


def test_run_daily_sync_all_success() -> None:
    patches = _patches_all_success(is_trading=True)
    _apply(patches)
    try:
        r = run_daily_sync(today=TODAY, session_factory=_make_session_factory(MagicMock()))
    finally:
        _tear(patches)

    assert isinstance(r, DailySyncReport)
    assert r.today == TODAY
    assert r.steps == {
        "stock_basic": "SUCCESS",
        "trade_cal": "SUCCESS",
        "kline": "SUCCESS",
        "market_cap": "SUCCESS",
    }
    assert r.quota_exhausted is False


def test_run_daily_sync_daily_update_skipped_on_non_trading_day() -> None:
    patches = _patches_all_success(is_trading=False)
    _apply(patches)
    try:
        r = run_daily_sync(today=TODAY, session_factory=_make_session_factory(MagicMock()))
    finally:
        _tear(patches)

    assert r.steps["kline"] == "SKIPPED"
    assert r.steps["market_cap"] == "SKIPPED"


def test_step_failure_does_not_block_subsequent_steps() -> None:
    patches = _patches_all_success(is_trading=True)
    _apply(patches)
    try:
        with patch("app.services.scheduler.sync_stock_basic_from_tushare", side_effect=RuntimeError("db down")):
            r = run_daily_sync(today=TODAY, session_factory=_make_session_factory(MagicMock()))
    finally:
        _tear(patches)

    assert r.steps["stock_basic"] == "FAILED"
    assert "stock_basic" in r.errors
    assert r.steps["trade_cal"] == "SUCCESS"
    assert r.steps["kline"] == "SUCCESS"


def test_quota_exhausted_mid_run_stops_subsequent_steps() -> None:
    patches = _patches_all_success(is_trading=True)
    _apply(patches)
    try:
        with patch(
            "app.services.scheduler.sync_trade_calendar_from_tushare",
            side_effect=AdapterQuotaExceededError("quota"),
        ):
            r = run_daily_sync(today=TODAY, session_factory=_make_session_factory(MagicMock()))
    finally:
        _tear(patches)

    assert r.steps["stock_basic"] == "SUCCESS"
    assert r.steps["trade_cal"] == "FAILED"
    assert r.quota_exhausted is True
    assert "kline" not in r.steps
    assert "market_cap" not in r.steps


def test_tushare_session_quota_error_short_circuits() -> None:
    with patch(
        "app.services.scheduler.tushare_session",
        side_effect=AdapterQuotaExceededError("login quota"),
    ):
        r = run_daily_sync(today=TODAY, session_factory=_make_session_factory(MagicMock()))

    assert r.quota_exhausted is True
    assert r.steps == {}


def test_build_scheduler_disabled_returns_none() -> None:
    with patch("app.services.scheduler.settings") as fake_settings:
        fake_settings.scheduler_enabled = False
        fake_settings.scheduler_sw_enabled = False
        assert build_scheduler() is None


def test_build_scheduler_enabled_returns_scheduler() -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    with patch("app.services.scheduler.settings") as fake_settings:
        fake_settings.scheduler_enabled = True
        fake_settings.scheduler_hour = 2
        fake_settings.scheduler_minute = 30
        fake_settings.scheduler_sw_enabled = False
        s = build_scheduler()
        assert isinstance(s, AsyncIOScheduler)
        assert s.get_job("daily_sync") is not None
        assert s.get_job("sw_weekly_sync") is None


def test_build_scheduler_sw_enabled_registers_weekly_job() -> None:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    with patch("app.services.scheduler.settings") as fake_settings:
        fake_settings.scheduler_enabled = False
        fake_settings.scheduler_sw_enabled = True
        fake_settings.scheduler_sw_day_of_week = "sat"
        fake_settings.scheduler_sw_hour = 2
        fake_settings.scheduler_sw_minute = 7
        s = build_scheduler()
        assert isinstance(s, AsyncIOScheduler)
        assert s.get_job("sw_weekly_sync") is not None
        assert s.get_job("daily_sync") is None
