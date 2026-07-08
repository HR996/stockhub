"""Unit tests for sw_sync_service — mocks adapter + repos, checks orchestration."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.tushare_types import SWClassifyRow, SWMemberRow
from app.core.errors import AdapterAuthError, AdapterDataError, AdapterQuotaExceededError
from app.services.sw_sync_service import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    _hydrate_members,
    _index_classify,
    _index_l3_by_name,
    _validate_parent_chain,
    sync_sw_industry,
)


def _classify_rows() -> list[SWClassifyRow]:
    return [
        SWClassifyRow(
            index_code="801010.SI",
            industry_code="SW801010",
            industry_name="农林牧渔",
            level="L1",
            parent_code=None,
            is_pub=True,
            src="SW2021",
        ),
        SWClassifyRow(
            index_code="801011.SI",
            industry_code="SW801011",
            industry_name="种植业",
            level="L2",
            parent_code="SW801010",
            is_pub=True,
            src="SW2021",
        ),
        SWClassifyRow(
            index_code="801012.SI",
            industry_code="SW801012",
            industry_name="粮食种植",
            level="L3",
            parent_code="SW801011",
            is_pub=True,
            src="SW2021",
        ),
    ]


def test_index_classify_detects_duplicate_industry_code() -> None:
    dup = [
        *_classify_rows(),
        SWClassifyRow(
            index_code="801013.SI",
            industry_code="SW801012",  # duplicate industry_code
            industry_name="其他",
            level="L3",
            parent_code="SW801011",
            is_pub=True,
            src="SW2021",
        ),
    ]
    with pytest.raises(AdapterDataError, match="duplicate industry_code"):
        _index_classify(dup)


def test_validate_parent_chain_flags_missing_parent() -> None:
    rows = _classify_rows()
    rows[2] = SWClassifyRow(
        index_code="801012.SI",
        industry_code="SW801012",
        industry_name="粮食种植",
        level="L3",
        parent_code="SW999999",  # nonexistent parent
        is_pub=True,
        src="SW2021",
    )
    by_industry_code, _ = _index_classify(rows)
    with pytest.raises(AdapterDataError, match="not found"):
        _validate_parent_chain(rows, by_industry_code)


def test_validate_parent_chain_flags_wrong_parent_level() -> None:
    """An L3 whose parent_code points at an L1 (skipping L2) must fail."""
    rows = _classify_rows()
    rows[2] = SWClassifyRow(
        index_code="801012.SI",
        industry_code="SW801012",
        industry_name="粮食种植",
        level="L3",
        parent_code="SW801010",  # skips L2, points directly at L1
        is_pub=True,
        src="SW2021",
    )
    by_industry_code, _ = _index_classify(rows)
    with pytest.raises(AdapterDataError, match="expected L2"):
        _validate_parent_chain(rows, by_industry_code)


def test_hydrate_members_fills_l1_l2_denorm() -> None:
    rows = _classify_rows()
    by_industry_code, by_index_code = _index_classify(rows)
    by_l3_name = _index_l3_by_name(rows)
    members = [
        SWMemberRow(ts_code="600123.SH", l3_index_code="801012.SI", in_date=date(2020, 1, 1), out_date=None),
    ]
    outcome = _hydrate_members(members, by_index_code, by_industry_code, by_l3_name)
    assert len(outcome.hydrated) == 1
    m = outcome.hydrated[0]
    assert m.l1_index_code == "801010.SI"
    assert m.l1_name == "农林牧渔"
    assert m.l2_index_code == "801011.SI"
    assert m.l2_name == "种植业"
    assert m.l3_name == "粮食种植"
    assert not outcome.orphans
    assert not outcome.remapped


def test_hydrate_members_records_orphan_when_l3_unknown() -> None:
    rows = _classify_rows()
    by_industry_code, by_index_code = _index_classify(rows)
    by_l3_name = _index_l3_by_name(rows)
    members = [
        # unknown code AND no l3_name → cannot recover
        SWMemberRow(ts_code="600999.SH", l3_index_code="801099.SI", in_date=None, out_date=None),
    ]
    outcome = _hydrate_members(members, by_index_code, by_industry_code, by_l3_name)
    assert outcome.hydrated == []
    assert outcome.orphans == ["600999.SH"]
    assert outcome.remapped == []


def test_hydrate_members_remaps_by_l3_name_when_index_code_missing() -> None:
    """Tushare's index_member_all sometimes returns legacy SW2014 l3_codes
    (e.g. 850412.SI for 特钢Ⅲ) that are absent from the SW2021 catalog.
    When the member row carries the SW2021 l3_name, we recover it by name."""
    rows = _classify_rows()
    by_industry_code, by_index_code = _index_classify(rows)
    by_l3_name = _index_l3_by_name(rows)
    members = [
        SWMemberRow(
            ts_code="600123.SH",
            l3_index_code="850412.SI",  # not in SW2021 catalog
            in_date=date(2020, 1, 1),
            out_date=None,
            l3_name="粮食种植",           # but the name matches a SW2021 L3
        ),
    ]
    outcome = _hydrate_members(members, by_index_code, by_industry_code, by_l3_name)
    assert len(outcome.hydrated) == 1
    m = outcome.hydrated[0]
    # Recovered — the SW2021 canonical code is used, not the SW2014 legacy one.
    assert m.l3_index_code == "801012.SI"
    assert m.l3_name == "粮食种植"
    assert m.l2_name == "种植业"
    assert m.l1_name == "农林牧渔"
    assert outcome.orphans == []
    assert outcome.remapped == [("600123.SH", "850412.SI", "801012.SI")]


def test_hydrate_members_orphan_when_name_also_unknown() -> None:
    """If BOTH l3_index_code and l3_name miss the SW2021 catalog, it's a genuine orphan."""
    rows = _classify_rows()
    by_industry_code, by_index_code = _index_classify(rows)
    by_l3_name = _index_l3_by_name(rows)
    members = [
        SWMemberRow(
            ts_code="600999.SH",
            l3_index_code="801099.SI",
            in_date=None,
            out_date=None,
            l3_name="不存在的行业",
        ),
    ]
    outcome = _hydrate_members(members, by_index_code, by_industry_code, by_l3_name)
    assert outcome.hydrated == []
    assert outcome.orphans == ["600999.SH"]


def test_index_l3_by_name_flags_duplicate_names() -> None:
    dup = [
        *_classify_rows(),
        SWClassifyRow(
            index_code="801099.SI",
            industry_code="SW801099",
            industry_name="粮食种植",  # duplicate L3 name
            level="L3",
            parent_code="SW801011",
            is_pub=True,
            src="SW2021",
        ),
    ]
    with pytest.raises(AdapterDataError, match="duplicate L3 industry_name"):
        _index_l3_by_name(dup)


def test_sync_sw_industry_happy_path_writes_success() -> None:
    pro = MagicMock()
    classify_repo = MagicMock()
    member_repo = MagicMock()
    task_repo = MagicMock()

    classify_rows = _classify_rows()
    member_rows = [
        SWMemberRow(ts_code="600123.SH", l3_index_code="801012.SI", in_date=date(2020, 1, 1), out_date=None),
    ]
    with (
        patch("app.services.sw_sync_service.fetch_sw_classify", return_value=classify_rows),
        patch("app.services.sw_sync_service.fetch_sw_members", return_value=member_rows),
    ):
        result = sync_sw_industry(
            pro=pro,
            classify_repo=classify_repo,
            member_repo=member_repo,
            task_repo=task_repo,
            triggered_by="test",
            today=date(2026, 7, 8),
        )

    assert result.status == STATUS_SUCCESS
    assert result.classify_count == 3
    assert result.member_count == 1
    classify_repo.replace_all.assert_called_once()
    member_repo.replace_all.assert_called_once()
    # RUNNING first, SUCCESS last
    assert task_repo.upsert_by_key.call_count == 2
    final_row = task_repo.upsert_by_key.call_args_list[-1].args[0]
    assert final_row.status == STATUS_SUCCESS
    assert final_row.success_count == 1


def test_sync_sw_industry_maps_quota_error_to_failed() -> None:
    pro = MagicMock()
    classify_repo = MagicMock()
    member_repo = MagicMock()
    task_repo = MagicMock()

    with patch(
        "app.services.sw_sync_service.fetch_sw_classify",
        side_effect=AdapterQuotaExceededError("points"),
    ):
        result = sync_sw_industry(
            pro=pro,
            classify_repo=classify_repo,
            member_repo=member_repo,
            task_repo=task_repo,
            triggered_by="test",
            today=date(2026, 7, 8),
        )

    assert result.status == STATUS_FAILED
    classify_repo.replace_all.assert_not_called()
    member_repo.replace_all.assert_not_called()
    final_row = task_repo.upsert_by_key.call_args_list[-1].args[0]
    assert final_row.status == STATUS_FAILED
    assert "points" in final_row.error_summary["message"]


def test_sync_sw_industry_maps_auth_error_to_failed() -> None:
    pro = MagicMock()
    classify_repo = MagicMock()
    member_repo = MagicMock()
    task_repo = MagicMock()

    with patch(
        "app.services.sw_sync_service.fetch_sw_classify",
        side_effect=AdapterAuthError("no perms"),
    ):
        result = sync_sw_industry(
            pro=pro,
            classify_repo=classify_repo,
            member_repo=member_repo,
            task_repo=task_repo,
            triggered_by="test",
            today=date(2026, 7, 8),
        )
    assert result.status == STATUS_FAILED
    classify_repo.replace_all.assert_not_called()


def test_sync_sw_industry_aborts_when_too_many_orphans() -> None:
    pro = MagicMock()
    classify_repo = MagicMock()
    member_repo = MagicMock()
    task_repo = MagicMock()

    classify_rows = _classify_rows()
    # 100% of members are orphaned → well above the 5% threshold
    member_rows = [
        SWMemberRow(ts_code=f"6001{i:02d}.SH", l3_index_code="801099.SI", in_date=None, out_date=None)
        for i in range(20)
    ]
    with (
        patch("app.services.sw_sync_service.fetch_sw_classify", return_value=classify_rows),
        patch("app.services.sw_sync_service.fetch_sw_members", return_value=member_rows),
    ):
        result = sync_sw_industry(
            pro=pro,
            classify_repo=classify_repo,
            member_repo=member_repo,
            task_repo=task_repo,
            triggered_by="test",
            today=date(2026, 7, 8),
        )

    assert result.status == STATUS_FAILED
    classify_repo.replace_all.assert_not_called()
