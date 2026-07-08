"""Shenwan (SW) industry sync service — Tushare Pro `index_classify` + `index_member_all`.

Snapshot-only model (no versions). One idempotent call per day:
  RUNNING → fetch classify → validate parent chain → fetch members → hydrate L1/L2
  → replace both tables → SUCCESS. Any error path writes FAILED with error_summary.

Callers own the DB session and the tushare pro handle lifetimes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.adapters.tushare_adapter import fetch_sw_classify, fetch_sw_members
from app.adapters.tushare_types import SWClassifyRow, SWMemberRow
from app.core.errors import AdapterAuthError, AdapterDataError, AdapterQuotaExceededError
from app.repositories.factor_repo import FactorResultRepo
from app.repositories.sw_repo import (
    SWClassifyRecord,
    SWClassifyRepo,
    SWMemberRecord,
    SWMemberRepo,
)
from app.repositories.task_log_repo import TaskLogRepo, TaskLogRow

logger = logging.getLogger(__name__)

TASK_SW_INDUSTRY = "SYNC_SW_INDUSTRY"

STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"

# Fraction of member rows allowed to be orphaned (parent chain broken) before we abort.
_ORPHAN_ABORT_THRESHOLD = 0.05


@dataclass(frozen=True)
class SWSyncResult:
    task_type: str
    task_key: str
    status: str
    classify_count: int
    member_count: int
    orphan_count: int = 0
    error_message: str | None = None


@dataclass
class _HydrationOutcome:
    hydrated: list[SWMemberRecord] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    # (ts_code, source_l3_code_from_member, canonical_l3_code_from_classify) triplets
    # captured whenever we recover a member row by matching l3_name instead of l3_index_code.
    remapped: list[tuple[str, str, str]] = field(default_factory=list)
    # (ts_code, source_l3_code_from_member, canonical_l3_code_from_classify) triplets
    # captured whenever we recover a member row by matching l3_name instead of l3_index_code.
    remapped: list[tuple[str, str, str]] = field(default_factory=list)


def sync_sw_industry(
    pro: Any,
    classify_repo: SWClassifyRepo,
    member_repo: SWMemberRepo,
    task_repo: TaskLogRepo,
    triggered_by: str,
    today: date | None = None,
) -> SWSyncResult:
    today = today or datetime.now(UTC).date()
    task_key = f"{TASK_SW_INDUSTRY}:{today.isoformat()}"

    task_repo.upsert_by_key(
        TaskLogRow(
            task_type=TASK_SW_INDUSTRY,
            task_key=task_key,
            status=STATUS_RUNNING,
            created_by=triggered_by,
        )
    )

    try:
        classify_rows = fetch_sw_classify(pro)
        by_industry_code, by_index_code = _index_classify(classify_rows)
        by_l3_name = _index_l3_by_name(classify_rows)
        _validate_parent_chain(classify_rows, by_industry_code)

        l3_index_codes = [c.index_code for c in classify_rows if c.level == "L3"]
        member_rows = fetch_sw_members(pro, l3_index_codes)

        outcome = _hydrate_members(
            member_rows, by_index_code, by_industry_code, by_l3_name
        )
        orphan_ratio = len(outcome.orphans) / max(len(member_rows), 1)
        if orphan_ratio > _ORPHAN_ABORT_THRESHOLD:
            raise AdapterDataError(
                f"orphan members {len(outcome.orphans)}/{len(member_rows)} "
                f"exceed {_ORPHAN_ABORT_THRESHOLD:.0%} threshold"
            )

        classify_records = [_to_classify_record(r) for r in classify_rows]
        classify_repo.replace_all(classify_records)
        member_repo.replace_all(outcome.hydrated)
    except (AdapterAuthError, AdapterQuotaExceededError, AdapterDataError) as exc:
        logger.exception("sync_sw_industry adapter error: %s", exc)
        _write_failed(task_repo, task_key, triggered_by, exc)
        return SWSyncResult(
            task_type=TASK_SW_INDUSTRY,
            task_key=task_key,
            status=STATUS_FAILED,
            classify_count=0,
            member_count=0,
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("sync_sw_industry unexpected error: %s", exc)
        _write_failed(task_repo, task_key, triggered_by, exc)
        return SWSyncResult(
            task_type=TASK_SW_INDUSTRY,
            task_key=task_key,
            status=STATUS_FAILED,
            classify_count=0,
            member_count=0,
            error_message=str(exc),
        )

    error_summary: dict[str, Any] | None = None
    if outcome.orphans or outcome.remapped:
        error_summary = {}
        if outcome.orphans:
            error_summary["orphan_ts_codes_sample"] = outcome.orphans[:20]
            error_summary["orphan_count"] = len(outcome.orphans)
        if outcome.remapped:
            error_summary["name_remapped_count"] = len(outcome.remapped)
            error_summary["name_remapped_sample"] = outcome.remapped[:10]

    task_repo.upsert_by_key(
        TaskLogRow(
            task_type=TASK_SW_INDUSTRY,
            task_key=task_key,
            status=STATUS_SUCCESS,
            created_by=triggered_by,
            finished_at=datetime.now(UTC),
            expected_count=len(member_rows),
            success_count=len(outcome.hydrated),
            missing_count=len(outcome.orphans),
            error_count=0,
            error_summary=error_summary,
        )
    )
    FactorResultRepo(task_repo._session).mark_sw_stale_before(datetime.now(UTC))
    return SWSyncResult(
        task_type=TASK_SW_INDUSTRY,
        task_key=task_key,
        status=STATUS_SUCCESS,
        classify_count=len(classify_records),
        member_count=len(outcome.hydrated),
        orphan_count=len(outcome.orphans),
    )


def _index_classify(
    rows: list[SWClassifyRow],
) -> tuple[dict[str, SWClassifyRow], dict[str, SWClassifyRow]]:
    by_industry_code: dict[str, SWClassifyRow] = {}
    by_index_code: dict[str, SWClassifyRow] = {}
    for row in rows:
        if row.industry_code in by_industry_code:
            raise AdapterDataError(
                f"duplicate industry_code={row.industry_code} across classify rows"
            )
        if row.index_code in by_index_code:
            raise AdapterDataError(
                f"duplicate index_code={row.index_code} across classify rows"
            )
        by_industry_code[row.industry_code] = row
        by_index_code[row.index_code] = row
    return by_industry_code, by_index_code


def _index_l3_by_name(rows: list[SWClassifyRow]) -> dict[str, SWClassifyRow]:
    """Build a lookup of SW2021 L3 rows by industry_name.

    Used as a fallback when Tushare's `index_member_all` returns legacy SW2014
    l3 codes (e.g. `850412.SI` for 特钢Ⅲ instead of the SW2021 canonical
    `850401.SI`). SW2021 L3 names are unique so this map is unambiguous;
    a duplicate name would signal a genuine catalog bug and we raise.
    """
    out: dict[str, SWClassifyRow] = {}
    for row in rows:
        if row.level != "L3":
            continue
        if row.industry_name in out:
            raise AdapterDataError(
                f"duplicate L3 industry_name={row.industry_name!r} in classify catalog"
            )
        out[row.industry_name] = row
    return out


def _index_l3_by_name(rows: list[SWClassifyRow]) -> dict[str, SWClassifyRow]:
    """Build a lookup of SW2021 L3 rows by industry_name.

    Used as a fallback when Tushare's `index_member_all` returns legacy SW2014
    l3 codes (e.g. `850412.SI` for 特钢Ⅲ instead of the SW2021 canonical
    `850401.SI`). SW2021 L3 names are unique so this map is unambiguous;
    a duplicate name would signal a genuine catalog bug and we raise.
    """
    out: dict[str, SWClassifyRow] = {}
    for row in rows:
        if row.level != "L3":
            continue
        if row.industry_name in out:
            raise AdapterDataError(
                f"duplicate L3 industry_name={row.industry_name!r} in classify catalog"
            )
        out[row.industry_name] = row
    return out


def _validate_parent_chain(
    rows: list[SWClassifyRow], by_industry_code: dict[str, SWClassifyRow]
) -> None:
    for row in rows:
        if row.level == "L1":
            continue
        if not row.parent_code:
            raise AdapterDataError(
                f"{row.level} row {row.index_code} missing parent_code"
            )
        parent = by_industry_code.get(row.parent_code)
        if parent is None:
            raise AdapterDataError(
                f"{row.level} row {row.index_code} parent_code={row.parent_code} "
                "not found in classify catalog"
            )
        expected_parent_level = "L1" if row.level == "L2" else "L2"
        if parent.level != expected_parent_level:
            raise AdapterDataError(
                f"{row.level} row {row.index_code} parent has level={parent.level}, "
                f"expected {expected_parent_level}"
            )


def _hydrate_members(
    members: list[SWMemberRow],
    by_index_code: dict[str, SWClassifyRow],
    by_industry_code: dict[str, SWClassifyRow],
    by_l3_name: dict[str, SWClassifyRow],
) -> _HydrationOutcome:
    outcome = _HydrationOutcome()
    for m in members:
        l3 = _resolve_l3(m, by_index_code, by_l3_name, outcome)
        if l3 is None:
            outcome.orphans.append(m.ts_code)
            continue
        l2 = by_industry_code.get(l3.parent_code or "")
        if l2 is None or l2.level != "L2":
            outcome.orphans.append(m.ts_code)
            continue
        l1 = by_industry_code.get(l2.parent_code or "")
        if l1 is None or l1.level != "L1":
            outcome.orphans.append(m.ts_code)
            continue
        outcome.hydrated.append(
            SWMemberRecord(
                ts_code=m.ts_code,
                l1_index_code=l1.index_code,
                l1_name=l1.industry_name,
                l2_index_code=l2.index_code,
                l2_name=l2.industry_name,
                l3_index_code=l3.index_code,
                l3_name=l3.industry_name,
                in_date=m.in_date,
                out_date=m.out_date,
            )
        )
    if outcome.remapped:
        logger.info(
            "sync_sw_industry: recovered %d member rows via l3_name fallback "
            "(SW2014 → SW2021 remap). Sample: %s",
            len(outcome.remapped),
            outcome.remapped[:3],
        )
    return outcome


def _resolve_l3(
    m: SWMemberRow,
    by_index_code: dict[str, SWClassifyRow],
    by_l3_name: dict[str, SWClassifyRow],
    outcome: _HydrationOutcome,
) -> SWClassifyRow | None:
    """Look up an L3 classify row for a member.

    Primary key: `l3_index_code`. When that misses (e.g. Tushare returned a
    legacy SW2014 code), fall back to matching by `l3_name` against the SW2021
    catalog. Successful fallbacks are recorded in `outcome.remapped` so we can
    audit them via the task log.
    """
    l3 = by_index_code.get(m.l3_index_code)
    if l3 is not None and l3.level == "L3":
        return l3
    if not m.l3_name:
        return None
    remap = by_l3_name.get(m.l3_name)
    if remap is None:
        return None
    outcome.remapped.append((m.ts_code, m.l3_index_code, remap.index_code))
    return remap


def _to_classify_record(row: SWClassifyRow) -> SWClassifyRecord:
    return SWClassifyRecord(
        index_code=row.index_code,
        industry_code=row.industry_code,
        industry_name=row.industry_name,
        level=row.level,
        parent_code=row.parent_code,
        is_pub=row.is_pub,
        src=row.src,
    )


def _write_failed(
    task_repo: TaskLogRepo, task_key: str, triggered_by: str, exc: BaseException
) -> None:
    task_repo.upsert_by_key(
        TaskLogRow(
            task_type=TASK_SW_INDUSTRY,
            task_key=task_key,
            status=STATUS_FAILED,
            created_by=triggered_by,
            finished_at=datetime.now(UTC),
            error_summary={"message": str(exc), "type": type(exc).__name__},
        )
    )


__all__ = [
    "STATUS_FAILED",
    "STATUS_RUNNING",
    "STATUS_SUCCESS",
    "TASK_SW_INDUSTRY",
    "SWSyncResult",
    "sync_sw_industry",
]
