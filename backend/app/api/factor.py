"""Factor API for SW sector momentum."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.envelope import ok
from app.repositories.factor_repo import FactorConfigRepo
from app.services.factor_service import (
    FactorParams,
    calculate_factor,
    copy_config,
    create_config,
    get_children,
    get_result,
    get_sector_stocks,
    list_configs,
    list_results,
    recalculate,
    update_config,
)

router = APIRouter(prefix="/api/factor", tags=["factor"])


@router.post("/results")
def create_result(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok(calculate_factor(db, FactorParams.from_dict(payload), user))


@router.get("/results")
def results_list(
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    return ok(list_results(db))


@router.get("/results/{result_id}")
def result_detail(
    result_id: int,
    level: str | None = Query(None),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    return ok(get_result(db, result_id, level))


@router.get("/results/{result_id}/children")
def result_children(
    result_id: int,
    parent_level: str = Query(...),
    parent_sector_code: str = Query(...),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    return ok(get_children(db, result_id, parent_level, parent_sector_code))


@router.get("/results/{result_id}/sectors/{level}/{sector_code}/stocks")
def result_sector_stocks(
    result_id: int,
    level: str = Path(...),
    sector_code: str = Path(...),
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    _ = user
    return ok(get_sector_stocks(db, result_id, level, sector_code))


@router.post("/results/{result_id}/recalculate")
def result_recalculate(
    result_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok(recalculate(db, result_id, user))


@router.get("/configs")
def configs_list(
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok(list_configs(FactorConfigRepo(db), user))


@router.post("/configs")
def configs_create(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok(create_config(FactorConfigRepo(db), user, payload))


@router.patch("/configs/{config_id}")
def configs_update(
    config_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok(update_config(FactorConfigRepo(db), user, config_id, payload))


@router.post("/configs/{config_id}/copy")
def configs_copy(
    config_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    return ok(copy_config(FactorConfigRepo(db), user, config_id))


@router.delete("/configs/{config_id}")
def configs_delete(
    config_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
) -> dict:
    deleted = FactorConfigRepo(db).delete(config_id, user)
    return ok({"deleted": deleted})
