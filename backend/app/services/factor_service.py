"""SW2021 sector momentum factor service."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import NotFoundError, ValidationError
from app.models.k_line_daily import KLineDaily
from app.models.stock_adj_factor import StockAdjFactor
from app.models.stock_basic import StockBasic
from app.models.sw_industry import SWIndustryClassify, SWIndustryMember
from app.repositories.factor_repo import (
    FactorConfigRepo,
    FactorResultCreate,
    FactorResultRepo,
    FactorRowCreate,
    FactorStockCreate,
)
from app.repositories.trade_cal_repo import TradeCalRepo

MIN_MARKET_CAP = Decimal("10000000000")
MIN_LISTED_DAYS = 20
MIN_SECTOR_STOCK_COUNT = 5
LEVELS = ("L1", "L2", "L3")


@dataclass(frozen=True)
class FactorParams:
    basedate: str
    window: int = 20
    top_ratio: float = 0.15
    classification: str = "SW"
    level: str = "L2"
    return_method: str = "simple"
    score_method: str = "median_return_score"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FactorParams:
        return cls(
            basedate=str(data.get("basedate") or ""),
            window=int(data.get("window") or 20),
            top_ratio=float(data.get("top_ratio") or 0.15),
            classification=str(data.get("classification") or "SW"),
            level=str(data.get("level") or "L2"),
            return_method=str(data.get("return_method") or "simple"),
            score_method=str(data.get("score_method") or "median_return_score"),
        )

    def normalized(self) -> dict[str, Any]:
        return {
            "basedate": self.basedate,
            "window": self.window,
            "top_ratio": self.top_ratio,
            "classification": self.classification,
            "level": self.level,
            "return_method": self.return_method,
            "score_method": self.score_method,
        }


@dataclass
class _StockReturn:
    ts_code: str
    name: str
    l1_code: str | None
    l1_name: str | None
    l2_code: str | None
    l2_name: str | None
    l3_code: str | None
    l3_name: str | None
    stock_return: Decimal | None
    missing_reason: str | None
    is_top: bool = False


def calculate_factor(session: Session, params: FactorParams, username: str) -> dict[str, Any]:
    _validate_params(params)
    basedate = datetime.strptime(params.basedate, "%Y-%m-%d").date()
    trade_repo = TradeCalRepo(session)
    if not trade_repo.is_trading_day(basedate):
        raise ValidationError("VALIDATION_NOT_TRADING_DAY", "basedate must be a trading day")
    days = trade_repo.previous_trading_days(basedate, params.window + 1)
    if len(days) < params.window + 1:
        raise ValidationError("VALIDATION_INSUFFICIENT_TRADING_DAYS", "not enough trading days for window")
    start_date = days[0]

    stock_returns = _compute_stock_returns(session, params, start_date, basedate)
    if not stock_returns:
        raise ValidationError(
            "FACTOR_NO_CANDIDATE_STOCKS",
            "no stocks passed factor filters; check SW membership and kline data",
            detail={
                "hint": "temporary mode ignores market cap; make sure selected stocks have SW membership and qfq kline data",
            },
        )
    valid_returns = [r for r in stock_returns if r.stock_return is not None]
    if not valid_returns:
        missing_counts: dict[str, int] = {}
        for row in stock_returns:
            key = row.missing_reason or "UNKNOWN"
            missing_counts[key] = missing_counts.get(key, 0) + 1
        raise ValidationError(
            "FACTOR_NO_VALID_RETURNS",
            "candidate stocks exist but none have both start/end qfq prices",
            detail={"missing_counts": missing_counts, "start_date": start_date.isoformat(), "basedate": basedate.isoformat()},
        )
    top_count = max(1, math.ceil(params.top_ratio * len(valid_returns))) if valid_returns else 0
    top_codes = {
        r.ts_code
        for r in sorted(valid_returns, key=lambda x: x.stock_return or Decimal("-999"), reverse=True)[:top_count]
    }
    for row in stock_returns:
        row.is_top = row.ts_code in top_codes

    snapshot_at = _industry_snapshot_at(session)
    result_repo = FactorResultRepo(session)
    result = result_repo.create(
        FactorResultCreate(
            params=params.normalized(),
            basedate=basedate,
            start_date=start_date,
            classification="SW",
            industry_snapshot_at=snapshot_at,
            created_by=username,
        )
    )
    result_repo.insert_stocks(_stock_rows(result.id, stock_returns))
    result_repo.insert_rows(_aggregate_rows(result.id, params, stock_returns))
    session.flush()
    return get_result(session, result.id, params.level)


def get_result(session: Session, result_id: int, level: str | None = None) -> dict[str, Any]:
    repo = FactorResultRepo(session)
    result = repo.get(result_id)
    if result is None:
        raise NotFoundError(f"factor result {result_id} not found", code="NOT_FOUND")
    level = (level or result.params.get("level") or "L2").upper()
    _validate_level(level)
    rows = repo.rows_by_level(result_id, level)
    return {
        "result": _result_to_dict(result),
        "level": level,
        "rows": [_row_to_dict(r) for r in rows],
    }


def get_children(
    session: Session, result_id: int, parent_level: str, parent_sector_code: str
) -> dict[str, Any]:
    parent_level = parent_level.upper()
    if parent_level == "L1":
        child_level = "L2"
    elif parent_level == "L2":
        child_level = "L3"
    else:
        child_level = ""
    if not child_level:
        return {"result_id": result_id, "level": parent_level, "rows": []}
    rows = FactorResultRepo(session).child_rows(result_id, parent_sector_code, child_level)
    return {"result_id": result_id, "level": child_level, "rows": [_row_to_dict(r) for r in rows]}


def get_sector_stocks(
    session: Session, result_id: int, level: str, sector_code: str
) -> dict[str, Any]:
    level = level.upper()
    _validate_level(level)
    rows = FactorResultRepo(session).sector_stocks(result_id, level, sector_code)
    return {
        "result_id": result_id,
        "level": level,
        "sector_code": sector_code,
        "stocks": [_stock_to_dict(r) for r in rows],
    }


def list_results(session: Session) -> dict[str, Any]:
    rows = FactorResultRepo(session).list_results()
    return {"items": [_result_to_dict(r) for r in rows]}


def recalculate(session: Session, result_id: int, username: str) -> dict[str, Any]:
    result = FactorResultRepo(session).get(result_id)
    if result is None:
        raise NotFoundError(f"factor result {result_id} not found", code="NOT_FOUND")
    return calculate_factor(session, FactorParams.from_dict(result.params), username)


def list_configs(repo: FactorConfigRepo, owner: str) -> dict[str, Any]:
    return {"items": [_config_to_dict(c) for c in repo.list_for_owner(owner)]}


def create_config(repo: FactorConfigRepo, owner: str, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValidationError("VALIDATION_CONFIG_NAME_REQUIRED", "config name required")
    params = FactorParams.from_dict(payload.get("params") or {}).normalized()
    return _config_to_dict(repo.create(name, params, owner))


def update_config(repo: FactorConfigRepo, owner: str, config_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    normalized = FactorParams.from_dict(params).normalized() if isinstance(params, dict) else None
    obj = repo.update(config_id, owner, name=payload.get("name"), params=normalized)
    if obj is None:
        raise NotFoundError(f"factor config {config_id} not found", code="NOT_FOUND")
    return _config_to_dict(obj)


def copy_config(repo: FactorConfigRepo, owner: str, config_id: int) -> dict[str, Any]:
    obj = repo.get_for_owner(config_id, owner)
    if obj is None:
        raise NotFoundError(f"factor config {config_id} not found", code="NOT_FOUND")
    return _config_to_dict(repo.create(f"{obj.name} 副本", obj.params, owner))


def _validate_params(params: FactorParams) -> None:
    if params.classification != "SW":
        raise ValidationError("VALIDATION_UNSUPPORTED_CLASSIFICATION", "only SW is supported in v1")
    _validate_level(params.level)
    if params.window < 1 or params.window > 250:
        raise ValidationError("VALIDATION_INVALID_WINDOW", "window must be 1..250")
    if not (0 < params.top_ratio <= 1):
        raise ValidationError("VALIDATION_INVALID_TOP_RATIO", "top_ratio must be in (0, 1]")
    if params.return_method not in ("simple", "log"):
        raise ValidationError("VALIDATION_INVALID_RETURN_METHOD", "return_method must be simple/log")
    if params.score_method not in ("median_return_score", "top_count_score"):
        raise ValidationError("VALIDATION_INVALID_SCORE_METHOD", "invalid score_method")


def _validate_level(level: str) -> None:
    if level.upper() not in LEVELS:
        raise ValidationError("VALIDATION_INVALID_LEVEL", "level must be L1/L2/L3")


def _compute_stock_returns(
    session: Session, params: FactorParams, start_date, basedate
) -> list[_StockReturn]:
    listed_days = TradeCalRepo(session).list_range(date(1990, 1, 1), start_date)
    open_days = [d.cal_date for d in listed_days if d.is_open]

    StartK = aliased(KLineDaily)
    EndK = aliased(KLineDaily)
    StartF = aliased(StockAdjFactor)
    EndF = aliased(StockAdjFactor)
    stmt = (
        select(StockBasic, SWIndustryMember, StartK, EndK, StartF, EndF)
        .join(SWIndustryMember, SWIndustryMember.ts_code == StockBasic.ts_code, isouter=True)
        .join(StartK, (StartK.ts_code == StockBasic.ts_code) & (StartK.trade_date == start_date), isouter=True)
        .join(EndK, (EndK.ts_code == StockBasic.ts_code) & (EndK.trade_date == basedate), isouter=True)
        .join(StartF, (StartF.ts_code == StockBasic.ts_code) & (StartF.trade_date == start_date), isouter=True)
        .join(EndF, (EndF.ts_code == StockBasic.ts_code) & (EndF.trade_date == basedate), isouter=True)
        .where(
            StockBasic.is_common.is_(True),
            StockBasic.is_bj.is_(False),
            ~StockBasic.name.contains("指数"),
        )
        .order_by(StockBasic.ts_code)
    )
    rows = session.execute(stmt).all()
    out: list[_StockReturn] = []
    for row in rows:
        stock: StockBasic = row[0]
        member: SWIndustryMember | None = row[1]
        start_bar: KLineDaily | None = row[2]
        end_bar: KLineDaily | None = row[3]
        start_factor: StockAdjFactor | None = row[4]
        end_factor: StockAdjFactor | None = row[5]
        if stock.list_date is None:
            continue
        if sum(1 for d in open_days if d >= stock.list_date) < MIN_LISTED_DAYS:
            continue
        start_is_st = start_bar.is_st_row if start_bar is not None else None
        if (bool(start_is_st) if start_is_st is not None else stock.is_st):
            continue
        start_close = start_bar.close_raw if start_bar is not None else None
        end_close = end_bar.close_raw if end_bar is not None else None
        stock_return: Decimal | None = None
        missing_reason: str | None = None
        if member is None:
            missing_reason = "NO_INDUSTRY"
        elif start_close is None:
            missing_reason = "NO_START_PRICE"
        elif end_close is None:
            missing_reason = "NO_END_PRICE"
        elif start_factor is None or start_factor.adj_factor == 0:
            missing_reason = "NO_START_ADJ_FACTOR"
        elif end_factor is None or end_factor.adj_factor == 0:
            missing_reason = "NO_END_ADJ_FACTOR"
        elif Decimal(start_close) <= 0:
            missing_reason = "INVALID_START_PRICE"
        else:
            ratio = (
                Decimal(end_close) * end_factor.adj_factor
                / (Decimal(start_close) * start_factor.adj_factor)
            )
            if params.return_method == "simple":
                stock_return = ratio - Decimal("1")
            else:
                stock_return = Decimal(str(math.log(float(ratio))))
        out.append(
            _StockReturn(
                ts_code=stock.ts_code,
                name=stock.name,
                l1_code=member.l1_index_code if member else None,
                l1_name=member.l1_name if member else None,
                l2_code=member.l2_index_code if member else None,
                l2_name=member.l2_name if member else None,
                l3_code=member.l3_index_code if member else None,
                l3_name=member.l3_name if member else None,
                stock_return=stock_return,
                missing_reason=missing_reason,
            )
        )
    return out


def _aggregate_rows(
    result_id: int, params: FactorParams, stocks: list[_StockReturn]
) -> list[FactorRowCreate]:
    valid = [s for s in stocks if s.stock_return is not None]
    rows: list[FactorRowCreate] = []
    for level in LEVELS:
        grouped: dict[str, list[_StockReturn]] = defaultdict(list)
        names: dict[str, str] = {}
        parents: dict[str, str | None] = {}
        for stock in valid:
            code = getattr(stock, f"{level.lower()}_code")
            name = getattr(stock, f"{level.lower()}_name")
            if not code:
                continue
            grouped[code].append(stock)
            names[code] = name or code
            parents[code] = None if level == "L1" else (stock.l1_code if level == "L2" else stock.l2_code)
        for code, members in grouped.items():
            sector_stock_count = len(members)
            sector_top_stock_count = sum(1 for s in members if s.is_top)
            density = Decimal(sector_top_stock_count) / Decimal(sector_stock_count)
            med = Decimal(str(median([s.stock_return for s in members if s.stock_return is not None])))
            if params.score_method == "median_return_score":
                score = density * med
            else:
                score = density * Decimal(sector_top_stock_count)
            rows.append(
                FactorRowCreate(
                    result_id=result_id,
                    level=level,
                    sector_code=code,
                    sector_name=names[code],
                    parent_sector_code=parents[code],
                    sector_stock_count=sector_stock_count,
                    sector_top_stock_count=sector_top_stock_count,
                    top_density=density.quantize(Decimal("0.000001")),
                    median_return=med.quantize(Decimal("0.000001")),
                    momentum_score=score.quantize(Decimal("0.000001")),
                    small_sample_flag=sector_stock_count < MIN_SECTOR_STOCK_COUNT,
                )
            )
    return rows


def _stock_rows(result_id: int, stocks: list[_StockReturn]) -> list[FactorStockCreate]:
    return [
        FactorStockCreate(
            result_id=result_id,
            ts_code=s.ts_code,
            stock_name=s.name,
            l1_code=s.l1_code,
            l1_name=s.l1_name,
            l2_code=s.l2_code,
            l2_name=s.l2_name,
            l3_code=s.l3_code,
            l3_name=s.l3_name,
            stock_return=s.stock_return.quantize(Decimal("0.00000001")) if s.stock_return is not None else None,
            is_top=s.is_top,
            missing_reason=s.missing_reason,
        )
        for s in stocks
    ]


def _industry_snapshot_at(session: Session):
    c1 = session.execute(select(func.max(SWIndustryClassify.created_at))).scalar_one()
    c2 = session.execute(select(func.max(SWIndustryMember.created_at))).scalar_one()
    return max([x for x in (c1, c2) if x is not None], default=None)


def _result_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "params": row.params,
        "basedate": row.basedate.isoformat(),
        "start_date": row.start_date.isoformat(),
        "classification": row.classification,
        "industry_snapshot_at": row.industry_snapshot_at.isoformat() if row.industry_snapshot_at else None,
        "stale": row.stale,
        "stale_reason": row.stale_reason,
        "stale_at": row.stale_at.isoformat() if row.stale_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "created_by": row.created_by,
    }


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "result_id": row.result_id,
        "level": row.level,
        "sector_code": row.sector_code,
        "sector_name": row.sector_name,
        "parent_sector_code": row.parent_sector_code,
        "sector_stock_count": row.sector_stock_count,
        "sector_top_stock_count": row.sector_top_stock_count,
        "top_density": float(row.top_density),
        "median_return": float(row.median_return) if row.median_return is not None else None,
        "momentum_score": float(row.momentum_score),
        "small_sample_flag": row.small_sample_flag,
    }


def _stock_to_dict(row) -> dict[str, Any]:
    return {
        "ts_code": row.ts_code,
        "stock_name": row.stock_name,
        "l1_code": row.l1_code,
        "l1_name": row.l1_name,
        "l2_code": row.l2_code,
        "l2_name": row.l2_name,
        "l3_code": row.l3_code,
        "l3_name": row.l3_name,
        "stock_return": float(row.stock_return) if row.stock_return is not None else None,
        "is_top": row.is_top,
        "missing_reason": row.missing_reason,
    }


def _config_to_dict(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "params": row.params,
        "owner": row.owner,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
    }
