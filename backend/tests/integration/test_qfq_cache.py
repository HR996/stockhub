"""QFQ cache integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.repositories.adj_factor_repo import AdjFactorRepo, AdjFactorUpsertRow
from app.repositories.kline_repo import KLineRepo, KLineRow
from app.repositories.qfq_cache_repo import (
    QfqCacheRepo,
    rebuild_qfq_for_stock,
    refresh_qfq_cache_for_day,
)

pytestmark = pytest.mark.integration


def test_rebuild_uses_latest_factor_as_basedate(db) -> None:
    code = "600000.SH"
    KLineRepo(db).upsert_many([
        KLineRow(code, date(2024, 1, 2), close_raw=Decimal("10")),
        KLineRow(code, date(2024, 1, 3), close_raw=Decimal("12")),
    ])
    AdjFactorRepo(db).upsert_many([
        AdjFactorUpsertRow(code, date(2024, 1, 2), Decimal("1")),
        AdjFactorUpsertRow(code, date(2024, 1, 3), Decimal("2")),
    ])

    assert rebuild_qfq_for_stock(db, code) == 2
    rows = QfqCacheRepo(db).list_by_stock(
        code, date(2024, 1, 1), date(2024, 1, 31)
    )
    assert rows[0].close == Decimal("5")
    assert rows[1].close == Decimal("12")
    assert rows[0].base_date == date(2024, 1, 3)


def test_same_factor_only_appends_new_day(db) -> None:
    code = "000001.SZ"
    KLineRepo(db).upsert_many([
        KLineRow(code, date(2024, 1, 2), close_raw=Decimal("10")),
    ])
    AdjFactorRepo(db).upsert_many([
        AdjFactorUpsertRow(code, date(2024, 1, 2), Decimal("2")),
    ])
    rebuild_qfq_for_stock(db, code)

    KLineRepo(db).upsert_many([
        KLineRow(code, date(2024, 1, 3), close_raw=Decimal("11")),
    ])
    AdjFactorRepo(db).upsert_many([
        AdjFactorUpsertRow(code, date(2024, 1, 3), Decimal("2")),
    ])
    rebuilt, written = refresh_qfq_cache_for_day(
        db, date(2024, 1, 3), {code}
    )

    assert rebuilt == 0
    assert written == 1
    assert QfqCacheRepo(db).count_for_stock(code) == 2


def test_changed_factor_rebuilds_stock_history(db) -> None:
    code = "000002.SZ"
    KLineRepo(db).upsert_many([
        KLineRow(code, date(2024, 1, 2), close_raw=Decimal("10")),
    ])
    AdjFactorRepo(db).upsert_many([
        AdjFactorUpsertRow(code, date(2024, 1, 2), Decimal("1")),
    ])
    rebuild_qfq_for_stock(db, code)

    KLineRepo(db).upsert_many([
        KLineRow(code, date(2024, 1, 3), close_raw=Decimal("6")),
    ])
    AdjFactorRepo(db).upsert_many([
        AdjFactorUpsertRow(code, date(2024, 1, 3), Decimal("2")),
    ])
    rebuilt, written = refresh_qfq_cache_for_day(
        db, date(2024, 1, 3), {code}
    )

    assert rebuilt == 1
    assert written == 2
    rows = QfqCacheRepo(db).list_by_stock(
        code, date(2024, 1, 1), date(2024, 1, 31)
    )
    assert rows[0].close == Decimal("5")
    assert rows[1].close == Decimal("6")
