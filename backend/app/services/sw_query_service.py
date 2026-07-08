"""Shenwan (SW) industry query helpers — read-only, back the /api/industry/* endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.models.data_update_task import DataUpdateTask
from app.repositories.sw_repo import SWClassifyRepo, SWMemberRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.services.sw_sync_service import TASK_SW_INDUSTRY


@dataclass(frozen=True)
class IndustryL3Node:
    index_code: str
    industry_code: str
    industry_name: str
    stock_count: int


@dataclass(frozen=True)
class IndustryL2Node:
    index_code: str
    industry_code: str
    industry_name: str
    children: list[IndustryL3Node]


@dataclass(frozen=True)
class IndustryL1Node:
    index_code: str
    industry_code: str
    industry_name: str
    children: list[IndustryL2Node]


@dataclass(frozen=True)
class IndustryTree:
    src: str
    levels: list[IndustryL1Node]


@dataclass(frozen=True)
class StockIndustry:
    ts_code: str
    l1_index_code: str
    l1_name: str
    l2_index_code: str
    l2_name: str
    l3_index_code: str
    l3_name: str
    in_date: date | None
    out_date: date | None


@dataclass(frozen=True)
class NodeStockRow:
    ts_code: str
    name: str | None
    l1_index_code: str
    l1_name: str
    l2_index_code: str
    l2_name: str
    l3_index_code: str
    l3_name: str
    in_date: date | None


@dataclass(frozen=True)
class NodeStockList:
    level: str
    index_code: str
    industry_name: str
    total: int
    stocks: list[NodeStockRow]


@dataclass(frozen=True)
class LastSyncInfo:
    status: str | None
    started_at: datetime | None
    finished_at: datetime | None
    classify_expected: int | None
    classify_success: int | None
    orphan_count: int | None
    error_message: str | None


def get_industry_tree(
    classify_repo: SWClassifyRepo,
    member_repo: SWMemberRepo,
) -> IndustryTree:
    """Assemble L1 → L2 → L3 tree with per-L3 stock counts."""
    rows = list(classify_repo.list_all())
    if not rows:
        return IndustryTree(src="SW2021", levels=[])

    l1_rows = [r for r in rows if r.level == "L1"]
    l2_rows = [r for r in rows if r.level == "L2"]
    l3_rows = [r for r in rows if r.level == "L3"]

    l3_stock_counts = _count_members_by_l3(member_repo)

    l3_by_parent: dict[str, list[IndustryL3Node]] = {}
    for l3 in l3_rows:
        if not l3.parent_code:
            continue
        l3_by_parent.setdefault(l3.parent_code, []).append(
            IndustryL3Node(
                index_code=l3.index_code,
                industry_code=l3.industry_code,
                industry_name=l3.industry_name,
                stock_count=l3_stock_counts.get(l3.index_code, 0),
            )
        )

    l2_by_parent: dict[str, list[IndustryL2Node]] = {}
    for l2 in l2_rows:
        if not l2.parent_code:
            continue
        l3_children = sorted(
            l3_by_parent.get(l2.industry_code, []), key=lambda x: x.index_code
        )
        l2_by_parent.setdefault(l2.parent_code, []).append(
            IndustryL2Node(
                index_code=l2.index_code,
                industry_code=l2.industry_code,
                industry_name=l2.industry_name,
                children=l3_children,
            )
        )

    src = l1_rows[0].src if l1_rows else "SW2021"
    l1_nodes: list[IndustryL1Node] = []
    for l1 in sorted(l1_rows, key=lambda x: x.index_code):
        l2_children = sorted(
            l2_by_parent.get(l1.industry_code, []), key=lambda x: x.index_code
        )
        l1_nodes.append(
            IndustryL1Node(
                index_code=l1.index_code,
                industry_code=l1.industry_code,
                industry_name=l1.industry_name,
                children=l2_children,
            )
        )
    return IndustryTree(src=src, levels=l1_nodes)


def _count_members_by_l3(member_repo: SWMemberRepo) -> dict[str, int]:
    """Aggregate member counts per L3 index_code with a single grouped select."""
    from sqlalchemy import func, select

    from app.models.sw_industry import SWIndustryMember

    stmt = select(
        SWIndustryMember.l3_index_code,
        func.count(SWIndustryMember.id),
    ).group_by(SWIndustryMember.l3_index_code)
    result = member_repo._session.execute(stmt)
    return {row[0]: int(row[1]) for row in result.all()}


def get_stock_industry(
    member_repo: SWMemberRepo, ts_code: str
) -> StockIndustry | None:
    row = member_repo.get_by_ts_code(ts_code)
    if row is None:
        return None
    return StockIndustry(
        ts_code=row.ts_code,
        l1_index_code=row.l1_index_code,
        l1_name=row.l1_name,
        l2_index_code=row.l2_index_code,
        l2_name=row.l2_name,
        l3_index_code=row.l3_index_code,
        l3_name=row.l3_name,
        in_date=row.in_date,
        out_date=row.out_date,
    )


def get_stocks_under_node(
    classify_repo: SWClassifyRepo,
    member_repo: SWMemberRepo,
    level: str,
    index_code: str,
) -> NodeStockList | None:
    """Return all stocks belonging to a given L1/L2/L3 node.

    LEFT JOINs `stock_basic.name` so names track the daily basic sync. Returns
    None if `index_code` doesn't exist in the classify catalog at that level.
    """
    level = level.upper()
    if level not in ("L1", "L2", "L3"):
        return None
    classify_row = classify_repo.get_by_index_code(index_code)
    if classify_row is None or classify_row.level != level:
        return None

    pairs = member_repo.list_stocks_by_node(level, index_code)
    stocks = [
        NodeStockRow(
            ts_code=m.ts_code,
            name=name,
            l1_index_code=m.l1_index_code,
            l1_name=m.l1_name,
            l2_index_code=m.l2_index_code,
            l2_name=m.l2_name,
            l3_index_code=m.l3_index_code,
            l3_name=m.l3_name,
            in_date=m.in_date,
        )
        for m, name in pairs
    ]
    return NodeStockList(
        level=level,
        index_code=index_code,
        industry_name=classify_row.industry_name,
        total=len(stocks),
        stocks=stocks,
    )


def get_last_sync_info(task_repo: TaskLogRepo) -> LastSyncInfo:
    task: DataUpdateTask | None = task_repo.latest_by_type(TASK_SW_INDUSTRY)
    if task is None:
        return LastSyncInfo(
            status=None,
            started_at=None,
            finished_at=None,
            classify_expected=None,
            classify_success=None,
            orphan_count=None,
            error_message=None,
        )
    error_message: str | None = None
    summary: dict[str, Any] | None = task.error_summary
    if task.status == "FAILED" and summary:
        error_message = str(summary.get("message"))
    return LastSyncInfo(
        status=task.status,
        started_at=task.started_at,
        finished_at=task.finished_at,
        classify_expected=task.expected_count,
        classify_success=task.success_count,
        orphan_count=task.missing_count,
        error_message=error_message,
    )


__all__ = [
    "IndustryL1Node",
    "IndustryL2Node",
    "IndustryL3Node",
    "IndustryTree",
    "LastSyncInfo",
    "NodeStockList",
    "NodeStockRow",
    "StockIndustry",
    "get_industry_tree",
    "get_last_sync_info",
    "get_stock_industry",
    "get_stocks_under_node",
]
