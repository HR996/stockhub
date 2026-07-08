"""Unit tests for sw_repo and sw_query_service — pure in-memory-ish (no external services)."""

from __future__ import annotations

from datetime import date

import pytest

from app.repositories.sw_repo import (
    SWClassifyRecord,
    SWClassifyRepo,
    SWMemberRecord,
    SWMemberRepo,
)
from app.services.sw_query_service import (
    get_industry_tree,
    get_last_sync_info,
    get_stock_industry,
)

pytestmark = pytest.mark.integration  # requires real DB (uses `db` fixture)


def _seed_classify(repo: SWClassifyRepo) -> None:
    repo.replace_all([
        SWClassifyRecord(
            index_code="801010.SI", industry_code="SW801010",
            industry_name="农林牧渔", level="L1", parent_code=None,
            is_pub=True, src="SW2021",
        ),
        SWClassifyRecord(
            index_code="801011.SI", industry_code="SW801011",
            industry_name="种植业", level="L2", parent_code="SW801010",
            is_pub=True, src="SW2021",
        ),
        SWClassifyRecord(
            index_code="801012.SI", industry_code="SW801012",
            industry_name="粮食种植", level="L3", parent_code="SW801011",
            is_pub=True, src="SW2021",
        ),
    ])


def test_classify_repo_replace_all_is_idempotent(db) -> None:
    repo = SWClassifyRepo(db)
    _seed_classify(repo)
    db.commit()
    assert len(list(repo.list_all())) == 3

    _seed_classify(repo)
    db.commit()
    assert len(list(repo.list_all())) == 3  # replaced, not appended


def test_classify_repo_list_by_level(db) -> None:
    repo = SWClassifyRepo(db)
    _seed_classify(repo)
    db.commit()
    assert len(list(repo.list_by_level("L1"))) == 1
    assert len(list(repo.list_by_level("L3"))) == 1


def test_member_repo_replace_all_and_lookup(db) -> None:
    classify = SWClassifyRepo(db)
    _seed_classify(classify)
    members = SWMemberRepo(db)
    members.replace_all([
        SWMemberRecord(
            ts_code="600123.SH",
            l1_index_code="801010.SI", l1_name="农林牧渔",
            l2_index_code="801011.SI", l2_name="种植业",
            l3_index_code="801012.SI", l3_name="粮食种植",
            in_date=date(2020, 1, 1), out_date=None,
        ),
    ])
    db.commit()

    row = members.get_by_ts_code("600123.SH")
    assert row is not None
    assert row.l1_name == "农林牧渔"

    l3_members = list(members.list_by_l3_index_code("801012.SI"))
    assert len(l3_members) == 1
    assert l3_members[0].ts_code == "600123.SH"


def test_get_industry_tree_assembles_nested_structure(db) -> None:
    classify = SWClassifyRepo(db)
    members = SWMemberRepo(db)
    _seed_classify(classify)
    members.replace_all([
        SWMemberRecord(
            ts_code="600123.SH",
            l1_index_code="801010.SI", l1_name="农林牧渔",
            l2_index_code="801011.SI", l2_name="种植业",
            l3_index_code="801012.SI", l3_name="粮食种植",
            in_date=None, out_date=None,
        ),
    ])
    db.commit()

    tree = get_industry_tree(classify, members)
    assert tree.src == "SW2021"
    assert len(tree.levels) == 1
    l1 = tree.levels[0]
    assert l1.industry_name == "农林牧渔"
    assert len(l1.children) == 1
    l2 = l1.children[0]
    assert len(l2.children) == 1
    l3 = l2.children[0]
    assert l3.stock_count == 1


def test_get_stock_industry_returns_none_for_unknown(db) -> None:
    members = SWMemberRepo(db)
    members.replace_all([])
    db.commit()
    assert get_stock_industry(members, "999999.SH") is None


def test_get_last_sync_info_empty_when_no_task(db) -> None:
    from app.repositories.task_log_repo import TaskLogRepo

    info = get_last_sync_info(TaskLogRepo(db))
    assert info.status is None
    assert info.started_at is None
