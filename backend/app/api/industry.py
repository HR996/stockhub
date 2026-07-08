"""Industry API — read-only Shenwan (SW2021) classification endpoints.

- GET /api/industry/tree          full L1→L2→L3 tree with per-L3 stock count
- GET /api/industry/stock/{ts}    a stock's L1/L2/L3 assignment (NOT_FOUND_STOCK if absent)
- GET /api/industry/last-sync     status of the most recent SYNC_SW_INDUSTRY task
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.envelope import fail, ok
from app.repositories.sw_repo import SWClassifyRepo, SWMemberRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.services.sw_query_service import (
    IndustryTree,
    LastSyncInfo,
    NodeStockList,
    StockIndustry,
    get_industry_tree,
    get_last_sync_info,
    get_stock_industry,
    get_stocks_under_node,
)

router = APIRouter(prefix="/api/industry", tags=["industry"])


def _tree_to_dict(tree: IndustryTree) -> dict:
    return {
        "src": tree.src,
        "levels": [
            {
                "index_code": l1.index_code,
                "industry_code": l1.industry_code,
                "industry_name": l1.industry_name,
                "children": [
                    {
                        "index_code": l2.index_code,
                        "industry_code": l2.industry_code,
                        "industry_name": l2.industry_name,
                        "children": [
                            {
                                "index_code": l3.index_code,
                                "industry_code": l3.industry_code,
                                "industry_name": l3.industry_name,
                                "stock_count": l3.stock_count,
                            }
                            for l3 in l2.children
                        ],
                    }
                    for l2 in l1.children
                ],
            }
            for l1 in tree.levels
        ],
    }


def _stock_to_dict(row: StockIndustry) -> dict:
    return {
        "ts_code": row.ts_code,
        "l1_index_code": row.l1_index_code,
        "l1_name": row.l1_name,
        "l2_index_code": row.l2_index_code,
        "l2_name": row.l2_name,
        "l3_index_code": row.l3_index_code,
        "l3_name": row.l3_name,
        "in_date": row.in_date.isoformat() if row.in_date else None,
        "out_date": row.out_date.isoformat() if row.out_date else None,
    }


def _last_sync_to_dict(info: LastSyncInfo) -> dict:
    return {
        "status": info.status,
        "started_at": info.started_at.isoformat() if info.started_at else None,
        "finished_at": info.finished_at.isoformat() if info.finished_at else None,
        "classify_expected": info.classify_expected,
        "classify_success": info.classify_success,
        "orphan_count": info.orphan_count,
        "error_message": info.error_message,
    }


def _node_stocks_to_dict(node: NodeStockList) -> dict:
    return {
        "level": node.level,
        "index_code": node.index_code,
        "industry_name": node.industry_name,
        "total": node.total,
        "stocks": [
            {
                "ts_code": s.ts_code,
                "name": s.name,
                "l1_index_code": s.l1_index_code,
                "l1_name": s.l1_name,
                "l2_index_code": s.l2_index_code,
                "l2_name": s.l2_name,
                "l3_index_code": s.l3_index_code,
                "l3_name": s.l3_name,
                "in_date": s.in_date.isoformat() if s.in_date else None,
            }
            for s in node.stocks
        ],
    }


def _node_stocks_to_dict(node: NodeStockList) -> dict:
    return {
        "level": node.level,
        "index_code": node.index_code,
        "industry_name": node.industry_name,
        "total": node.total,
        "stocks": [
            {
                "ts_code": s.ts_code,
                "name": s.name,
                "l1_index_code": s.l1_index_code,
                "l1_name": s.l1_name,
                "l2_index_code": s.l2_index_code,
                "l2_name": s.l2_name,
                "l3_index_code": s.l3_index_code,
                "l3_name": s.l3_name,
                "in_date": s.in_date.isoformat() if s.in_date else None,
            }
            for s in node.stocks
        ],
    }


@router.get("/tree")
def industry_tree(
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    tree = get_industry_tree(SWClassifyRepo(db), SWMemberRepo(db))
    return ok(_tree_to_dict(tree))


@router.get("/stock/{ts_code}")
def stock_industry(
    ts_code: str = Path(..., min_length=1, max_length=16),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    _ = user
    row = get_stock_industry(SWMemberRepo(db), ts_code)
    if row is None:
        return JSONResponse(
            status_code=200,
            content=fail(
                "NOT_FOUND_STOCK",
                f"ts_code={ts_code} not found in SW industry membership",
                detail={"ts_code": ts_code},
            ),
        )
    return ok(_stock_to_dict(row))


@router.get("/last-sync")
def industry_last_sync(
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    info = get_last_sync_info(TaskLogRepo(db))
    return ok(_last_sync_to_dict(info))


@router.get("/node/{level}/{index_code}/stocks")
def industry_node_stocks(
    level: str = Path(..., description="L1 / L2 / L3"),
    index_code: str = Path(..., min_length=1, max_length=32),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    _ = user
    level_upper = level.upper()
    if level_upper not in ("L1", "L2", "L3"):
        return JSONResponse(
            status_code=200,
            content=fail(
                "VALIDATION_INVALID_LEVEL",
                f"level must be L1/L2/L3, got {level!r}",
                detail={"level": level},
            ),
        )
    node = get_stocks_under_node(
        SWClassifyRepo(db), SWMemberRepo(db), level_upper, index_code
    )
    if node is None:
        return JSONResponse(
            status_code=200,
            content=fail(
                "NOT_FOUND_INDUSTRY_NODE",
                f"no {level_upper} industry with index_code={index_code}",
                detail={"level": level_upper, "index_code": index_code},
            ),
        )
    return ok(_node_stocks_to_dict(node))
