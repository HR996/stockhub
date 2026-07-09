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
6. 全部交易日提交后构建 `k_line_qfq_latest` 展示缓存

每个交易日独立提交并输出进度。重复执行会跳过已经成功的日期；使用 `--force` 可强制重抓。

### 日常单日更新

```bash
python -m app.data_service update --date 2026-07-08
```

### 只同步基础表

```bash
python -m app.data_service sync-basic
python -m app.data_service sync-calendar --start 2026-01-01 --end 2026-12-31
```

### 重建最新前复权缓存

```bash
python -m app.data_service rebuild-qfq-cache
python -m app.data_service rebuild-qfq-cache --ts-code 600000.SH
```

## Legacy Baostock Scripts

以下脚本仍保留，但不再是默认数据链路：

- `init_data.py`
- `sync_kline.py`

新链路使用 Tushare `daily + daily_basic + adj_factor`，权威 K 线只保存未复权数据。
