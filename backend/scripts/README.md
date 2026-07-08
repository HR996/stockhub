# backend/scripts

数据初始化和同步入口。默认数据源已切换为 Tushare；旧 Baostock 脚本保留为 legacy/回滚参考。

## 前置条件

```bash
cd backend
export DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock'
export TUSHARE_TOKEN='<your-token>'
uv run alembic upgrade head
```

## Tushare Data Service

推荐使用模块入口：

```bash
python -m app.data_service --help
```

兼容脚本入口：

```bash
python scripts/data_service.py --help
```

### 初始化两个月测试数据

```bash
python -m app.data_service init --start 2026-05-08 --end 2026-07-08
```

执行内容：

1. 同步 `stock_basic`
2. 同步 `trade_calendar`
3. 按交易日批量同步全市场 `daily`
4. 同步同日 `daily_basic` 并写入 `latest_market_cap`
5. 同步同日 `adj_factor` 并写入 `stock_adj_factor`
6. 用本地 raw 日线 + 复权因子重算 `k_line_daily` 的 qfq/hfq 列

### 日常单日更新

```bash
python -m app.data_service update --date 2026-07-08
```

### 只同步基础表

```bash
python -m app.data_service sync-basic
python -m app.data_service sync-calendar --start 2026-01-01 --end 2026-12-31
```

### 重算复权价格

```bash
python -m app.data_service recompute-adjusted --start 2026-05-08 --end 2026-07-08
```

## Legacy Baostock Scripts

以下脚本仍保留，但不再是默认数据链路：

- `init_data.py`
- `sync_kline.py`

新链路使用 Tushare `daily + daily_basic + adj_factor`，按交易日批量同步全市场数据，不再按股票逐只请求 qfq/hfq。
