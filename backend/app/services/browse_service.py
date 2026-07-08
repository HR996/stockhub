"""Whitelisted generic table browsing service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, String, func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.browse_history import BrowseHistory
from app.models.data_update_task import DataUpdateTask
from app.models.factor import FactorConfig, FactorResult, FactorResultRow, FactorResultStock
from app.models.k_line_daily import KLineDaily
from app.models.latest_market_cap import LatestMarketCap
from app.models.stock_adj_factor import StockAdjFactor
from app.models.stock_basic import StockBasic
from app.models.sw_industry import SWIndustryClassify, SWIndustryMember
from app.models.trade_calendar import TradeCalendar

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


@dataclass(frozen=True)
class FieldSpec:
    key: str
    title: str
    data_type: str
    description: str
    sortable: bool = True
    filterable: bool = True


@dataclass(frozen=True)
class TableSpec:
    key: str
    title: str
    description: str
    model: type
    fields: tuple[FieldSpec, ...]


def f(key: str, title: str, data_type: str, desc: str) -> FieldSpec:
    return FieldSpec(key, title, data_type, desc)


TABLES: dict[str, TableSpec] = {
    "stock_basic": TableSpec(
        "stock_basic", "股票基础信息", "A 股股票代码、名称、市场、上市状态和基础标记。", StockBasic,
        (
            f("id", "ID", "number", "内部主键"),
            f("ts_code", "股票代码", "string", "TuShare 格式股票代码"),
            f("bs_code", "Baostock 代码", "string", "baostock 格式股票代码"),
            f("name", "名称", "string", "股票名称"),
            f("market", "市场", "string", "SH/SZ/BJ"),
            f("list_date", "上市日期", "date", "上市日期"),
            f("delist_date", "退市日期", "date", "退市日期"),
            f("is_bj", "北交所", "boolean", "是否北交所"),
            f("is_common", "普通股票", "boolean", "是否普通股票"),
            f("is_st", "ST", "boolean", "最新 ST 标记"),
            f("updated_at", "更新时间", "datetime", "最后同步时间"),
        ),
    ),
    "trade_calendar": TableSpec(
        "trade_calendar", "交易日历", "交易日与非交易日标记。", TradeCalendar,
        (f("id", "ID", "number", "内部主键"), f("cal_date", "日期", "date", "日历日期"), f("is_open", "交易日", "boolean", "是否开市"), f("updated_at", "更新时间", "datetime", "更新时间")),
    ),
    "k_line_daily": TableSpec(
        "k_line_daily", "日 K 线", "日线行情，包含不复权、前复权、后复权三组价格。", KLineDaily,
        tuple(f(k, k, "number" if k not in ("ts_code", "trade_date", "updated_at") else ("string" if k == "ts_code" else "date"), k) for k in (
            "id", "ts_code", "trade_date", "open_raw", "high_raw", "low_raw", "close_raw",
            "open_qfq", "high_qfq", "low_qfq", "close_qfq", "open_hfq", "high_hfq",
            "low_hfq", "close_hfq", "volume", "amount", "turn", "pct_chg", "trade_status",
            "is_st_row", "updated_at",
        )),
    ),
    "latest_market_cap": TableSpec(
        "latest_market_cap", "最新市值", "由 Tushare daily_basic 写入的最新市值快照。", LatestMarketCap,
        tuple(f(k, k, "number" if k not in ("ts_code", "market_cap_source", "snapshot_date", "snapshot_at", "updated_at") else "string", k) for k in (
            "id", "ts_code", "total_market_cap", "circ_market_cap", "total_share", "liqa_share",
            "snapshot_close", "snapshot_date", "market_cap_source", "snapshot_at", "updated_at",
        )),
    ),
    "stock_adj_factor": TableSpec(
        "stock_adj_factor", "复权因子", "Tushare 复权因子，用于本地计算 qfq/hfq。", StockAdjFactor,
        tuple(f(k, k, "number" if k not in ("ts_code", "trade_date", "source", "updated_at") else ("date" if k == "trade_date" else "string"), k) for k in (
            "id", "ts_code", "trade_date", "adj_factor", "source", "updated_at",
        )),
    ),
    "data_update_task": TableSpec(
        "data_update_task", "数据更新任务", "后台同步任务执行记录。", DataUpdateTask,
        tuple(f(k, k, "string", k) for k in (
            "id", "task_type", "task_key", "status", "started_at", "finished_at",
            "expected_count", "success_count", "missing_count", "error_count", "created_by",
        )),
    ),
    "sw_industry_classify": TableSpec(
        "sw_industry_classify", "申万行业分类", "SW2021 行业树快照。", SWIndustryClassify,
        tuple(f(k, k, "string", k) for k in ("id", "index_code", "industry_code", "industry_name", "level", "parent_code", "is_pub", "src", "created_at")),
    ),
    "sw_industry_member": TableSpec(
        "sw_industry_member", "申万行业成分", "股票到 SW L1/L2/L3 的当前映射。", SWIndustryMember,
        tuple(f(k, k, "string", k) for k in ("id", "ts_code", "l1_index_code", "l1_name", "l2_index_code", "l2_name", "l3_index_code", "l3_name", "in_date", "out_date", "created_at")),
    ),
    "browse_history": TableSpec(
        "browse_history", "浏览历史", "用户保存的页面状态历史。", BrowseHistory,
        tuple(f(k, k, "string", k) for k in ("id", "username", "page_key", "page_title", "visited_at")),
    ),
    "factor_config": TableSpec(
        "factor_config", "因子配置", "用户保存的板块动量参数配置。", FactorConfig,
        tuple(f(k, k, "string", k) for k in ("id", "name", "owner", "created_at", "updated_at", "updated_by")),
    ),
    "factor_result": TableSpec(
        "factor_result", "因子结果头", "一次板块动量计算的参数和状态。", FactorResult,
        tuple(f(k, k, "string", k) for k in ("id", "basedate", "start_date", "classification", "industry_snapshot_at", "stale", "stale_reason", "created_at", "created_by")),
    ),
    "factor_result_row": TableSpec(
        "factor_result_row", "因子板块结果", "一次计算下各层级板块得分。", FactorResultRow,
        tuple(f(k, k, "string", k) for k in ("id", "result_id", "level", "sector_code", "sector_name", "parent_sector_code", "sector_stock_count", "sector_top_stock_count", "top_density", "median_return", "momentum_score", "small_sample_flag")),
    ),
    "factor_result_stock": TableSpec(
        "factor_result_stock", "因子个股快照", "一次计算下个股收益和行业归属快照。", FactorResultStock,
        tuple(f(k, k, "string", k) for k in ("id", "result_id", "ts_code", "stock_name", "l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name", "stock_return", "is_top", "missing_reason")),
    ),
}


def list_tables() -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "title": spec.title,
            "description": spec.description,
            "fields": [field.__dict__ for field in spec.fields],
        }
        for spec in TABLES.values()
    ]


def query_table(session: Session, table_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    spec = _table(table_key)
    field_map = {field.key: field for field in spec.fields}
    selected = payload.get("fields") or [field.key for field in spec.fields]
    if not isinstance(selected, list) or any(fld not in field_map for fld in selected):
        raise ValidationError("VALIDATION_INVALID_FIELD", "unknown selected field")

    page = int(payload.get("page") or 1)
    page_size = int(payload.get("page_size") or DEFAULT_PAGE_SIZE)
    if page < 1:
        raise ValidationError("VALIDATION_INVALID_PAGE", "page must be >= 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValidationError("VALIDATION_PAGE_SIZE_TOO_LARGE", f"page_size must be 1..{MAX_PAGE_SIZE}")

    stmt: Select = select(spec.model)
    stmt = _apply_filters(stmt, spec, payload.get("filters") or [])

    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

    order_by = payload.get("order_by") or selected[0]
    order = payload.get("order") or "asc"
    if order_by not in field_map:
        raise ValidationError("VALIDATION_INVALID_ORDER_FIELD", f"unknown order_by: {order_by}")
    if order not in ("asc", "desc"):
        raise ValidationError("VALIDATION_INVALID_ORDER", f"unknown order: {order}")
    col = getattr(spec.model, order_by)
    stmt = stmt.order_by(col.desc() if order == "desc" else col.asc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = session.execute(stmt).scalars().all()
    return {
        "items": [{field: _json(getattr(row, field)) for field in selected} for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "fields": selected,
    }


def _table(table_key: str) -> TableSpec:
    spec = TABLES.get(table_key)
    if spec is None:
        raise ValidationError("VALIDATION_INVALID_TABLE", f"unknown table: {table_key}")
    return spec


def _apply_filters(stmt: Select, spec: TableSpec, filters: list[Any]) -> Select:
    fields = {field.key for field in spec.fields}
    for item in filters:
        if not isinstance(item, dict):
            raise ValidationError("VALIDATION_INVALID_FILTER", "filter must be object")
        field = item.get("field")
        op = item.get("op")
        value = item.get("value")
        if field not in fields:
            raise ValidationError("VALIDATION_INVALID_FILTER_FIELD", f"unknown filter field: {field}")
        col = getattr(spec.model, field)
        if op == "eq":
            stmt = stmt.where(col == value)
        elif op == "contains":
            stmt = stmt.where(col.cast(String).ilike(f"%{value}%"))
        elif op == "gte":
            stmt = stmt.where(col >= value)
        elif op == "lte":
            stmt = stmt.where(col <= value)
        elif op == "is_null":
            stmt = stmt.where(col.is_(None) if value is not False else col.is_not(None))
        else:
            raise ValidationError("VALIDATION_INVALID_FILTER_OP", f"unknown filter op: {op}")
    return stmt


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value
