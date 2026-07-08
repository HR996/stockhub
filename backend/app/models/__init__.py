"""SQLAlchemy models — imported here so Alembic autogenerate can discover them."""

from app.core.db import Base
from app.models.browse_history import BrowseHistory
from app.models.data_update_task import DataUpdateTask
from app.models.factor import FactorConfig, FactorResult, FactorResultRow, FactorResultStock
from app.models.k_line_daily import KLineDaily
from app.models.latest_market_cap import LatestMarketCap
from app.models.stock_adj_factor import StockAdjFactor
from app.models.stock_basic import StockBasic
from app.models.sw_industry import SWIndustryClassify, SWIndustryMember
from app.models.trade_calendar import TradeCalendar

__all__ = [
    "Base",
    "BrowseHistory",
    "DataUpdateTask",
    "FactorConfig",
    "FactorResult",
    "FactorResultRow",
    "FactorResultStock",
    "KLineDaily",
    "LatestMarketCap",
    "SWIndustryClassify",
    "SWIndustryMember",
    "StockAdjFactor",
    "StockBasic",
    "TradeCalendar",
]
