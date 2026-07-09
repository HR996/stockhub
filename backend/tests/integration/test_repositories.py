"""P1-02 — Repository idempotency + 领域方法契约测试。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.stock_repo import StockBasicRepo, StockBasicRow
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow
from app.repositories.trade_cal_repo import TradeCalRepo, TradeCalRow

pytestmark = pytest.mark.integration


# ---------- stock_basic ----------

def test_stock_basic_upsert_is_idempotent(db) -> None:
    repo = StockBasicRepo(db)
    row = StockBasicRow(
        ts_code="600000.SH", bs_code="sh.600000", name="浦发银行", market="SH",
        list_date=date(1999, 11, 10), is_bj=False, is_common=True, is_st=False,
        updated_by="test",
    )
    assert repo.upsert_many([row]) == 1
    db.commit()
    assert repo.count() == 1

    # Re-run with same key → row count unchanged
    repo.upsert_many([row])
    db.commit()
    assert repo.count() == 1


def test_stock_basic_upsert_updates_mutable_fields(db) -> None:
    repo = StockBasicRepo(db)
    repo.upsert_many([
        StockBasicRow(ts_code="600000.SH", bs_code="sh.600000", name="老名字", market="SH")
    ])
    db.commit()

    repo.upsert_many([
        StockBasicRow(ts_code="600000.SH", bs_code="sh.600000", name="新名字", market="SH")
    ])
    db.commit()

    row = repo.get_by_ts_code("600000.SH")
    assert row is not None
    assert row.name == "新名字"


def test_stock_basic_get_by_ts_code_missing(db) -> None:
    repo = StockBasicRepo(db)
    assert repo.get_by_ts_code("999999.XX") is None


# ---------- trade_calendar ----------

def test_trade_cal_upsert_is_idempotent(db) -> None:
    repo = TradeCalRepo(db)
    rows = [
        TradeCalRow(cal_date=date(2026, 1, d), is_open=(d not in (2, 3)))
        for d in range(1, 8)
    ]
    assert repo.upsert_many(rows) == 7
    db.commit()
    assert repo.count() == 7

    repo.upsert_many(rows)
    db.commit()
    assert repo.count() == 7


def test_trade_cal_previous_trading_days(db) -> None:
    repo = TradeCalRepo(db)
    repo.upsert_many([
        TradeCalRow(cal_date=date(2026, 1, 1), is_open=False),
        TradeCalRow(cal_date=date(2026, 1, 2), is_open=True),
        TradeCalRow(cal_date=date(2026, 1, 3), is_open=True),
        TradeCalRow(cal_date=date(2026, 1, 4), is_open=False),
        TradeCalRow(cal_date=date(2026, 1, 5), is_open=True),
        TradeCalRow(cal_date=date(2026, 1, 6), is_open=True),
    ])
    db.commit()

    # 3 交易日回溯 from 2026-01-06
    result = repo.previous_trading_days(date(2026, 1, 6), 3)
    assert result == [date(2026, 1, 3), date(2026, 1, 5), date(2026, 1, 6)]

    assert repo.is_trading_day(date(2026, 1, 3)) is True
    assert repo.is_trading_day(date(2026, 1, 4)) is False
    assert repo.is_trading_day(date(2026, 1, 99 % 30)) is False  # missing date


# ---------- k_line_daily ----------

def _kline_row(day: int) -> KLineRow:
    return KLineRow(
        ts_code="600000.SH",
        trade_date=date(2026, 1, day),
        trade_status=1,
        close_raw=Decimal("10.00"),
        volume=Decimal("1000000"),
    )


def test_kline_upsert_is_idempotent(db) -> None:
    repo = KLineRepo(db)
    rows = [_kline_row(d) for d in range(2, 7)]
    assert repo.upsert_many(rows) == 5
    db.commit()
    assert repo.count() == 5

    repo.upsert_many(rows)
    db.commit()
    assert repo.count() == 5


def test_kline_upsert_updates_price_columns(db) -> None:
    repo = KLineRepo(db)
    repo.upsert_many([_kline_row(2)])
    db.commit()

    updated = KLineRow(
        ts_code="600000.SH",
        trade_date=date(2026, 1, 2),
        trade_status=1,
        close_raw=Decimal("11.11"),
    )
    repo.upsert_many([updated])
    db.commit()

    row = repo.get("600000.SH", date(2026, 1, 2))
    assert row is not None
    assert row.close_raw == Decimal("11.1100")


def test_kline_list_by_stock_range(db) -> None:
    repo = KLineRepo(db)
    repo.upsert_many([_kline_row(d) for d in range(2, 8)])
    db.commit()

    result = repo.list_by_stock("600000.SH", date(2026, 1, 3), date(2026, 1, 5))
    assert [r.trade_date for r in result] == [
        date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5),
    ]


# ---------- data_update_task ----------

def test_task_log_upsert_by_key_is_idempotent(db) -> None:
    repo = TaskLogRepo(db)
    row = TaskLogRow(
        task_type="SYNC_KLINE",
        task_key="SYNC_KLINE:2026-07-07",
        status="SUCCESS",
        created_by="scheduler",
        finished_at=datetime(2026, 7, 7, 8, 0, tzinfo=UTC),
        expected_count=5000,
        success_count=4998,
        missing_count=2,
        error_count=0,
    )
    id1 = repo.upsert_by_key(row)
    db.commit()
    assert repo.count() == 1

    id2 = repo.upsert_by_key(row)
    db.commit()
    assert repo.count() == 1
    assert id1 == id2


def test_task_log_upsert_by_key_overwrites_status(db) -> None:
    repo = TaskLogRepo(db)
    running = TaskLogRow(
        task_type="SYNC_KLINE",
        task_key="SYNC_KLINE:2026-07-07",
        status="RUNNING",
        created_by="scheduler",
    )
    repo.upsert_by_key(running)
    db.commit()

    finished = TaskLogRow(
        task_type="SYNC_KLINE",
        task_key="SYNC_KLINE:2026-07-07",
        status="SUCCESS",
        created_by="scheduler",
        finished_at=datetime(2026, 7, 7, 8, 0, tzinfo=UTC),
    )
    repo.upsert_by_key(finished)
    db.commit()

    found = repo.find_by_key("SYNC_KLINE", "SYNC_KLINE:2026-07-07")
    assert found is not None
    assert found.status == "SUCCESS"
    assert repo.count() == 1


def test_task_log_create_without_key(db) -> None:
    """Ad-hoc task with no idempotency key — always creates a new row."""
    repo = TaskLogRepo(db)
    row = TaskLogRow(task_type="MANUAL_TRIGGER", status="SUCCESS", created_by="alice")
    repo.create(row)
    repo.create(row)
    db.commit()
    assert repo.count() == 2


def test_task_log_latest_by_type(db) -> None:
    repo = TaskLogRepo(db)
    repo.create(TaskLogRow(task_type="SYNC_KLINE", status="FAILED", created_by="scheduler"))
    repo.create(TaskLogRow(task_type="SYNC_KLINE", status="SUCCESS", created_by="scheduler"))
    db.commit()

    latest = repo.latest_by_type("SYNC_KLINE")
    assert latest is not None
    assert latest.status == "SUCCESS"
