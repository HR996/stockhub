# istock

**面向少量用户的 A 股量化分析 Web 系统**。v1 目标：数据基座 + 数据健康 + 数据浏览 + 股票详情 + 申万分类维护 + 板块动量因子。

单机、少并发、"数据基座 + 分析工具"混合定位；不追求高并发、不做交易、不做实时行情。

---

## 目录

- [架构一览](#架构一览)
- [Quick Start（本地开发）](#quick-start本地开发)
- [Quick Start（Docker）](#quick-startdocker)
- [常用命令速查](#常用命令速查)
- [功能清单与进度](#功能清单与进度)
- [如何验收 P1-01](#如何验收-p1-01)
- [如何验收 P1-02](#如何验收-p1-02)
- [如何验收 P1-03](#如何验收-p1-03)
- [如何验收 P1-04](#如何验收-p1-04)
- [如何验收 P1-05](#如何验收-p1-05)
- [如何验收 P1-06](#如何验收-p1-06)
- [如何验收 P1-07](#如何验收-p1-07)
- [如何验收 P2-01](#如何验收-p2-01)
- [如何验收 P2-02](#如何验收-p2-02)
- [如何验收 P2-03](#如何验收-p2-03)
- [如何验收 P2-04](#如何验收-p2-04)
- [如何验收 P2-05](#如何验收-p2-05)
- [如何验收 P2-06](#如何验收-p2-06)
- [文档索引](#文档索引)
- [部署步骤](#部署步骤)
- [目录结构](#目录结构)

---

## 架构一览

```
frontend (React 18 + Vite 5 + AntD 5)
      │  REST + envelope {success, data, message}
      ▼
backend (FastAPI + SQLAlchemy 2.x)
      │
      ├── adapters       (tushare / baostock legacy)
      ├── data_service   (Tushare 初始化 / 增量更新 / 复权重算)
      ├── services       (业务编排)
      ├── repositories   (数据访问)
      ├── factors        (板块动量因子)
      └── core           (config / db / envelope / errors)
      │
      ▼
PostgreSQL 15
```

技术选型详见 [`docs/04_TECH_STACK.md`](docs/04_TECH_STACK.md)；模块划分见 [`docs/03_MODULES.md`](docs/03_MODULES.md)；表结构见 [`docs/05_DATA_MODEL.md`](docs/05_DATA_MODEL.md)。

---

## Quick Start（本地开发）

**推荐路径**。适合边写代码边调试。

### 前置要求

| 工具 | 版本 | 安装 |
| --- | --- | --- |
| Python | ≥ 3.11 | 系统包管理器或 pyenv |
| **uv** | 最新 | `pip install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | ≥ 20 LTS | nvm / 官方安装包 |
| PostgreSQL | 15+ | 本地装或用 `docker run` 起单容器（见下） |

### 1. 起 PostgreSQL

```bash
docker run -d --name istock-pg \
  -e POSTGRES_USER=istock \
  -e POSTGRES_PASSWORD=istock \
  -e POSTGRES_DB=istock \
  -p 5432:5432 \
  postgres:15
```

### 2. 起后端

```bash
cd backend
uv sync --group dev                     # 装依赖到 .venv/
cp .env.example .env                    # 按需修改 DATABASE_URL

export DATABASE_URL=postgresql+psycopg://istock:istock@localhost:5432/istock
uv run uvicorn app.main:app --reload --port 8000
```

访问：
- API 根：http://localhost:8000/api/health
- OpenAPI 文档：http://localhost:8000/api/docs

### 3. 起前端

```bash
cd frontend
npm install
npm run dev                             # Vite 默认 5173
```

访问：http://localhost:5173

**关于 API 代理**：Vite dev server 的 `/api` 前缀会被代理到后端。target 由环境变量 `VITE_API_TARGET` 控制：

- **本地场景**（宿主机跑 uvicorn + vite）：默认 `http://localhost:8000`，无需配置
- **Docker 场景**：`docker-compose.yml` 已注入 `http://backend:8000`
- 如需自定义（例如后端跑在其他机器）：`cd frontend && cp .env.example .env` 后修改

---

## Quick Start（Docker）

**一键起完整栈**：postgres + backend + frontend。适合验收和演示。

```bash
docker-compose up --build
```

访问：
- 前端：http://localhost:5173
- 后端 API：http://localhost:8000/api/health
- OpenAPI 文档：http://localhost:8000/api/docs
- PostgreSQL：`localhost:5432`（用户名 / 密码 / 库名 均为 `istock`）

停止：`docker-compose down`；清空数据卷：`docker-compose down -v`。

---

## 常用命令速查

### 后端（在 `backend/` 目录）

| 场景 | 命令 |
| --- | --- |
| 装依赖 | `uv sync --group dev` |
| 增加依赖 | `uv add <pkg>` |
| 增加开发依赖 | `uv add --group dev <pkg>` |
| 移除依赖 | `uv remove <pkg>` |
| 启动服务 | `uv run uvicorn app.main:app --reload --port 8000` |
| 跑全部测试 | `uv run pytest` |
| 跑单元测试（跳过外部依赖） | `uv run pytest -m "not integration"` |
| 跑集成测试 | `uv run pytest -m integration` |
| Lint | `uv run ruff check app/ tests/` |
| Lint 自动修复 | `uv run ruff check --fix app/ tests/` |
| 类型检查 | `uv run mypy app/` |
| Alembic 迁移（P1-02 后可用） | `uv run alembic upgrade head` |
| Tushare 初始化两个月测试数据 | `TUSHARE_TOKEN=... uv run python -m app.data_service init --start 2026-05-08 --end 2026-07-08` |
| Tushare 单日更新 | `TUSHARE_TOKEN=... uv run python -m app.data_service update --date 2026-07-08` |

### 前端（在 `frontend/` 目录）

| 场景 | 命令 |
| --- | --- |
| 装依赖 | `npm install` |
| 启动 | `npm run dev` |
| 生产构建 | `npm run build` |
| 类型检查 | `npm run typecheck` |
| Lint | `npm run lint` |

---

## 功能清单与进度

### 图例

- ✅ done — 已实现且验证通过
- 🚧 in_progress — 正在实现
- ⏳ pending — 未开始
- ⏸️ blocked — 有阻塞

### Phase 1 · 数据基座（7 / 7 完成 — Phase 1 收官）

| ID | 任务 | 状态 |
| --- | --- | --- |
| P1-01 | 项目骨架 + `/api/health` 端点 | ✅ |
| P1-02 | PostgreSQL + Alembic + 4 张核心表（stock_basic / trade_calendar / k_line_daily / data_update_task） | ✅ |
| P1-03 | baostock adapter | ✅ |
| P1-04 | 最新市值 adapter + 合成 service（baostock 单源） | ✅ |
| P1-05 | stock_basic + trade_cal 同步 Service | ✅ |
| P1-06 | K 线同步 Service（三口径） | ✅ |
| P1-07 | 数据健康 API v0（`GET /api/health/summary`） | ✅ |

### Phase 2 · 数据健康（6 / 6 完成 — Phase 2 收官）

| ID | 任务 | 状态 |
| --- | --- | --- |
| P2-01 | K 线月历数据 Service | ✅ |
| P2-02 | 单日健康详情 Service | ✅ |
| P2-03 | 定时任务调度（APScheduler） | ✅ |
| P2-04 | 健康 API 完整版 | ✅ |
| P2-05 | 前端脚手架 + 登录桩 + AntD 布局 | ✅ |
| P2-06 | Dashboard 页面（真数据） | ✅ |

### 后续 Phase（未详规）

| Phase | 内容 | 状态 |
| --- | --- | --- |
| Phase 3 | 数据浏览（表列表 / 通用表 / 字段控制 / 浏览历史 / 股票详情） | ✅ |
| Phase 4 | 申万分类维护（上传 / 解析 / 校验 / 预览 / 写入 / 版本 / 回滚） | ⏳ |
| Phase 5 | 板块动量因子（参数配置 / 计算 / 结果失效） | ✅ |
| Phase 6 | 体验完善（异常日志 / 添加用户 / UI 打磨） | ⏳ |

任务全量清单与颗粒度定义见 [`docs/06_TASKS.md`](docs/06_TASKS.md)。

---

## 如何验收 P1-01

**目标**：确认后端启动、`/api/health` 端点返回符合 envelope 规范、前端能加载并展示后端返回。

### 方式 A：本地开发（快）

```bash
cd backend
uv sync --group dev
uv run pytest                                    # 应看到 1 passed
uv run ruff check app/ tests/                    # 应看到 All checks passed!
uv run uvicorn app.main:app --port 8000 &
curl -s http://localhost:8000/api/health | python -m json.tool
```

预期返回：

```json
{
    "success": true,
    "data": {
        "app": "istock",
        "version": "0.1.0",
        "server_time": "<ISO 8601>"
    },
    "message": ""
}
```

前端：

```bash
cd frontend && npm install && npm run dev
```

打开 http://localhost:5173 —— 应看到"服务健康检查"卡片，展示 app / version / server_time 三行 Descriptions。

### 方式 B：Docker（一键）

```bash
docker-compose up --build
```

浏览器访问 http://localhost:5173，同上。

### 通过标准

- [x] `uv run pytest` 通过（`test_health_returns_envelope`）
- [x] `uv run ruff check` 全绿
- [x] `curl /api/health` 返回符合 envelope 的 200 响应
- [x] OpenAPI 文档在 `/api/docs` 可访问，列出 `/api/health`
- [x] 前端首页能拉到后端 `/api/health` 数据并展示三行卡片

---

## 如何验收 P1-02

**目标**：确认 4 张核心表在 PostgreSQL 中建立，Repository 幂等 upsert 与领域查询正常工作。

### 前置

需要 PostgreSQL 15 起在 `localhost:5432`（或修改 `DATABASE_URL`）：

```bash
# 若尚未起 pg：
docker run -d --name istock-pg -e POSTGRES_USER=istock -e POSTGRES_PASSWORD=istock \
  -e POSTGRES_DB=istock -p 5432:5432 postgres:15
```

### 步骤

```bash
cd backend
uv sync --group dev
export DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock'
export TEST_DATABASE_URL="$DATABASE_URL"

uv run alembic upgrade head                # 应看到：Running upgrade  -> 0001, initial: 4 core tables
uv run pytest -v                           # 应看到：13 passed（1 unit + 12 integration）
uv run ruff check app/ tests/              # 应看到：All checks passed!
```

### 验证表结构

```bash
uv run python -c "
import psycopg
with psycopg.connect('postgresql://istock:istock@localhost:5432/istock') as conn, conn.cursor() as cur:
    cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name\")
    for r in cur.fetchall(): print(r[0])
"
```

预期输出：`alembic_version / data_update_task / k_line_daily / stock_basic / trade_calendar`

### 通过标准

- [x] `alembic upgrade head` 干净通过
- [x] 4 张表 + `alembic_version` 均已创建
- [x] `k_line_daily` 有 3 组复权字段（`*_raw` / `*_qfq` / `*_hfq`）
- [x] `data_update_task` 有部分唯一索引 `uq_data_update_task_type_key`（`WHERE task_key IS NOT NULL`）
- [x] 4 个 Repository 均支持幂等 `upsert_many`（同参数重复调用行数不变）
- [x] `TradeCalRepo.previous_trading_days` 按交易日历回溯（不按自然日）
- [x] `TaskLogRepo.upsert_by_key` 用相同 `task_key` 覆盖既有行；无 `task_key` 时 `create` 每次新建行
- [x] `pytest` 13 个测试全绿；`ruff check` 无告警

---

## 如何验收 P1-03

**目标**：确认 baostock 适配器能真接口获取股票基础信息、交易日历、K 线（三种复权口径），并正确处理停牌日空价格与错误码。

### 步骤

```bash
cd backend
uv sync --group dev

# 单元测试（无网络）— 验证 helper 与错误映射
uv run pytest tests/unit/test_baostock_adapter.py -v         # 应看到 7 passed

# 集成测试（真接口）— 打通 baostock 全链路
uv run pytest tests/integration/test_baostock_adapter.py -v   # 应看到 5 passed（约 15s）

# 完整套件
uv run pytest -v                                              # 应看到 25 passed
uv run ruff check app/ tests/                                 # 应看到 All checks passed!
```

### 手工探针（可选）

```bash
uv run python -c "
from datetime import date
from app.adapters.baostock_adapter import baostock_session, fetch_kline, ADJUST_QFQ

with baostock_session():
    rows = fetch_kline('sh.600000', date(2024, 1, 2), date(2024, 1, 5), ADJUST_QFQ)

for r in rows:
    print(r.trade_date, r.close, r.trade_status)
"
```

### 通过标准

- [x] `baostock_session` context manager：登录失败抛 `AdapterAuthError`，网络异常抛 `AdapterConnectionError`；无论异常都保证 `logout`
- [x] `fetch_stock_basic('sh.600000')` 返回 1 条 `StockBasicRow`，`ts_code=='600000.SH'`、`market=='SH'`、`is_bj is False`
- [x] `fetch_trade_cal(2024-01-01, 2024-01-31)` 返回 31 条；2024-01-01 元旦 `is_open=False`，2024-01-02 交易日 `is_open=True`
- [x] `fetch_kline` 三种 `adjustflag`（`1=hfq / 2=qfq / 3=raw`）返回相同的日期集合，价格不同
- [x] 停牌日（`trade_status=0`）价格字段全为 `None`（不是 `Decimal(0)`）
- [x] baostock 返回 `error_code != '0'` 时抛 `AdapterDataError`，异常消息包含调用的接口名
- [x] 单文件 <200 行（当前 `baostock_adapter.py` = 183 行；DTO 独立到 `baostock_types.py`）
- [x] Adapter **不写数据库**，返回纯 dataclass 结构

---

## 如何验收 P1-04

**目标**：确认 baostock 市值合成路径（`totalShare × close_raw`）能真接口打通、覆盖缺失场景、幂等 upsert 到 `latest_market_cap`。

> 背景：初版计划走 akshare 兜底最新市值，但实测东财 push 端点在本环境持续拒绝匿名请求（`RemoteDisconnected`）。方案改为 **baostock 单源合成**（`query_profit_data.totalShare × k_line_daily.close_raw`）。ADR-16 已修订，akshare 依赖已从 `pyproject.toml` 移除。

### 步骤

```bash
cd backend
uv sync --group dev
export DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock'
export TEST_DATABASE_URL="$DATABASE_URL"

# 应用两个 P1-04 相关迁移（0002 建表 + 0003 加 total_share/liqa_share/snapshot_close/snapshot_date）
uv run alembic upgrade head

# 单元测试（无网络，用 fake ResultSet + mock adapter）
uv run pytest tests/unit/test_baostock_profit.py -v      # 4 passed
uv run pytest tests/unit/test_market_cap_service.py -v   # 2 passed

# 集成测试（Postgres 必须可达；不需网络）
uv run pytest tests/integration/test_market_cap_repo.py -v      # 3 passed
uv run pytest tests/integration/test_market_cap_service.py -v   # 5 passed

# 全套（含 baostock 真接口测试 test_fetch_profit_data_returns_total_share）
uv run pytest -v                                                # 40 passed
uv run ruff check app/ tests/                                   # All checks passed!
```

### 手工探针（可选，需 baostock 可达）

```bash
uv run python -c "
from app.adapters.baostock_adapter import baostock_session
from app.adapters.baostock_profit import fetch_profit_data
with baostock_session():
    row = fetch_profit_data('sh.600000', year=2024, quarter=4)
print(row)
# 期望: ProfitDataRow(bs_code='sh.600000', pub_date=..., stat_date=..., total_share=Decimal('~29352178302.00'), ...)
"
```

### 通过标准

- [x] `alembic upgrade head` 应用 `0002_add_latest_market_cap` + `0003_market_cap_from_baostock` 干净通过
- [x] `latest_market_cap` 表含 `total_market_cap` / `circ_market_cap` / `total_share` / `liqa_share` / `snapshot_close` / `snapshot_date` / `market_cap_source` 字段
- [x] `market_cap_source` 枚举 = `baostock_synth`（合成成功）/ `baostock_missing`（profit 或 K 线缺失）
- [x] `fetch_profit_data` 真接口对 `sh.600000` 返回 `total_share` 在 200~400 亿股区间
- [x] `synthesize_for` 对样本股正确合成 `total_market_cap = total_share × close_raw`（浦发 293 亿 × 10 元 ≈ 2935 亿）
- [x] Profit 或 K 线缺任一侧时该股 `market_cap_source='baostock_missing'`；service 不 crash 整批
- [x] Adapter 抛异常时 service 记 warning 并把该股标为 missing（不阻塞后续股票）
- [x] `MarketCapRepo.upsert_many` 幂等（同 `(ts_code)` 重复调用行数不变）
- [x] `MarketCapRepo.count_missing` 只统计 `total_market_cap IS NULL` 的行
- [x] `pytest` 40 passed；`ruff check` 无告警
- [x] `pyproject.toml` 已移除 `akshare>=1.12` 依赖；`prompt/reference/akshare_cheatsheet.md` 已删除
- [x] **ADR-06 与 ADR-16 修订**已录入 `docs/04_TECH_STACK.md §11`

---

## 如何验收 P1-05

**目标**：确认 stock_basic + trade_cal 同步服务能真接口打通、幂等 upsert、写 `data_update_task` 状态转换。附带发现的 PG 参数上限问题（65535）已通过 Repository 分批解决。

### 步骤

```bash
cd backend
uv sync --group dev
export DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock'
export TEST_DATABASE_URL="$DATABASE_URL"

# 单元测试（无网络）
uv run pytest tests/unit/test_sync_basic_service.py -v         # 8 passed

# 集成测试（真 baostock + 真 PG）
uv run pytest tests/integration/test_sync_basic_service.py -v  # 4 passed（约 20s）

# 全套
uv run pytest -v                                               # 52 passed
uv run ruff check app/ tests/                                  # All checks passed!
```

### 手工探针（可选，需 baostock 与 PG 可达）

```bash
uv run python -c "
from datetime import date
from app.core.db import session_scope
from app.adapters.baostock_adapter import baostock_session
from app.repositories.stock_repo import StockBasicRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.services.sync_basic_service import sync_stock_basic

with baostock_session(), session_scope() as db:
    r = sync_stock_basic(StockBasicRepo(db), TaskLogRepo(db), triggered_by='manual', today=date(2026, 7, 7))
    print(r)
"
```

### 通过标准

- [x] 全市场 stock_basic（4000+ 条）成功入库；`success_count == expected_count`
- [x] `trade_calendar` 支持自定义 range 与默认 range（近 3 年 + 明年年底）
- [x] 二次跑同一 `today` → 表行数不变；`data_update_task` 只有 1 条对应 `task_key` 的记录（`RUNNING → SUCCESS` 覆盖式更新）
- [x] Adapter 抛异常时 service 记 `FAILED`（不 raise 到调用者，返回 `SyncResult`）
- [x] ST 判定从名称推导（含 `ST` / `*ST` / `SST`）
- [x] Repository upsert 分批执行（PG 65535 参数上限修复：`core/db.py::chunked` 工具 + 4 个 Repository 均改造）
- [x] `pytest` 52 passed；`ruff check` 无告警
- [x] Service 单文件 <220 行；不写 SQL / 不调 Adapter 底层

---

## 如何验收 P1-06

**目标**：确认 K 线同步能一次拉三种复权口径并合并入库、幂等、正确处理停牌与缺失、写完整 `data_update_task` 明细。

### 步骤

```bash
cd backend
uv sync --group dev
export DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock'
export TEST_DATABASE_URL="$DATABASE_URL"

# 单元测试（无网络）
uv run pytest tests/unit/test_sync_kline_service.py -v          # 7 passed

# 集成测试（真 baostock + 真 PG，20 支 × 9 交易日）
uv run pytest tests/integration/test_sync_kline_service.py -v   # 4 passed（约 5s）

# 全套（session-scoped baostock login，避免黑名单）
uv run pytest -v                                                # 63 passed（约 2min）
uv run ruff check app/ tests/                                   # All checks passed!
```

### 手工探针（可选，需 baostock 与 PG 可达）

```bash
uv run python -c "
from datetime import date
from app.core.db import session_scope
from app.adapters.baostock_adapter import baostock_session
from app.repositories.kline_repo import KLineRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.services.sync_kline_service import sync_kline_for_stocks

with baostock_session(), session_scope() as db:
    r = sync_kline_for_stocks(
        ts_codes=['600000.SH', '000001.SZ', '600519.SH'],
        start_date=date(2024, 1, 2), end_date=date(2024, 1, 12),
        kline_repo=KLineRepo(db), task_repo=TaskLogRepo(db),
        triggered_by='manual', today=date(2026, 7, 7),
    )
    print(r)
"
```

### 通过标准

- [x] 单支股票的三种复权口径合并到 **k_line_daily 一行 3 组字段**（`*_raw` / `*_qfq` / `*_hfq`）
- [x] 20 支样本股 × 9 个交易日入库；`success_count == 20`、`error_count == 0`
- [x] 停牌日：`trade_status=0`、价格字段全 None（不是 `Decimal(0)`）
- [x] 幂等：同 `(today, start, end, stocks)` 二次跑不产生新行；`data_update_task` 单条覆盖
- [x] 部分失败识别：单支异常 → `PARTIAL`；全部异常 → `FAILED`；全成功 → `SUCCESS`
- [x] `data_update_task.error_summary` 记录前 20 个 error / missing 股票代码
- [x] `expected_count / success_count / missing_count / error_count` 全部有值
- [x] `pytest` 63 passed；`ruff check` 无告警
- [x] Service 单文件 <220 行；不写 SQL / 不调外部服务底层
- [x] **测试基础设施升级**：`bs_session` fixture 提到 `tests/conftest.py`，scope=session（避开 baostock `10001011 黑名单用户`）

---

## 如何验收 P1-07

**目标**：确认 `GET /api/health/summary` 端点能聚合 4 张核心表 + 任务日志的 `count` / `last_updated`，符合 envelope 契约，覆盖空表与非空场景。

### 步骤

```bash
cd backend
source .venv/bin/activate
uv sync --group dev
export DATABASE_URL='postgresql+psycopg://istock:istock@localhost:5432/istock'
export TEST_DATABASE_URL="$DATABASE_URL"

# 单元 + 集成 contract 测试
pytest tests/unit/test_health_api.py tests/integration/test_health_api.py -v   # 4 passed

# 完整套件
pytest tests/ -v                                                                # 65+ passed
ruff check app/ tests/                                                          # All checks passed!
```

### 手工验证

```bash
# 起 uvicorn（单独窗口）
uvicorn app.main:app --port 8000 &

# 空表状态
curl -s http://localhost:8000/api/health/summary | python -m json.tool
# 期望：所有表 count=0, last_updated=null

# 灌入一些数据后再查（略）
```

### 通过标准

- [x] `GET /api/health/summary` 返回 `{success: true, data: {stock_basic:{count,last_updated}, trade_calendar:{...}, k_line_daily:{...}, latest_market_cap:{...}, latest_task:{...}}, message: ""}`
- [x] envelope 合规（`success` / `data` / `message` 三段式）
- [x] 空表场景：`count=0`、`last_updated=null`
- [x] 灌入数据后：`count` 正确统计，`last_updated` 是 ISO 8601 带时区
- [x] `X-User` header 被接受（v1 存根，不校验；真校验 P2-05）
- [x] `pytest` 65+ passed；`ruff check` 无告警
- [x] Service 只读、无 SQL 直接拼接、按 `docs/03_MODULES.md` 分层
- [x] **测试基础设施**：`bs_session` fixture 在 baostock 黑名单时优雅 `pytest.skip`（不 error）

---

## 如何验收 P2-01

**目标**：确认 `health_calendar_service.get_calendar(year, month)` 能按 US-3.2 六条 EARS 正确判定日状态（green / yellow / red / gray + has_anomaly）；纯 Service 层，不打网络、不写 DB。

### 步骤

```bash
cd backend
source .venv/bin/activate
uv sync --group dev

# 只跑本任务用例
pytest tests/unit/test_health_calendar.py -v      # 应看到 9 passed

# 全套 unit（不需 PG）
pytest tests/unit/ -q                              # 应看到 41 passed
ruff check app/ tests/                             # All checks passed!
```

### 手工探针（可选，需 PG + 少量样本数据）

```bash
uv run python -c "
from app.core.db import session_scope
from app.repositories.kline_repo import KLineRepo
from app.repositories.stock_repo import StockBasicRepo
from app.repositories.trade_cal_repo import TradeCalRepo
from app.services.health_calendar_service import get_calendar

with session_scope() as db:
    r = get_calendar(2024, 1, TradeCalRepo(db), StockBasicRepo(db), KLineRepo(db))
    for d in r.days:
        print(d.cal_date, d.status, d.expected, d.actual, d.has_anomaly)
"
```

### 通过标准

- [x] `get_calendar(year, month)` 返回 `CalendarMonth(year, month, days=[DayStatus, ...])`；`days` 长度 = 该月自然日数（覆盖跨月首末日）
- [x] 非交易日（`trade_calendar.is_open=False` 或无行）→ `status=gray`、`expected=0`、`actual=0`
- [x] 交易日且 `actual == expected` → `green`
- [x] 交易日且 `0 < actual < expected` → `yellow`
- [x] 交易日且 `actual == 0` → `red`
- [x] `has_anomaly` 独立于 `status`：仅当存在 `trade_status != 0 AND close_raw IS NULL` 的行时置真；停牌行（`trade_status=0`，价格 null）**不算异常**
- [x] Repository 新增方法只暴露领域行为（`StockBasicRepo.count_active_at` / `KLineRepo.distinct_stock_counts_by_date_range` / `KLineRepo.anomaly_dates_in_range`），无 ORM Query 泄漏
- [x] Service 不写 DB、不调 baostock；`pytest tests/unit/test_health_calendar.py` 9 passed；`ruff check` 全绿

---

## 如何验收 P2-02

**目标**：确认 `health_day_service.get_day_detail(day)` 能对单日给出 expected / success / missing / error 计数、缺失与异常股票列表、以及覆盖该日的最近 K 线任务摘要；非交易日抛 `NotFoundError`。

### 步骤

```bash
cd backend
source .venv/bin/activate
uv sync --group dev

# 只跑本任务用例
pytest tests/unit/test_health_day.py -v            # 应看到 8 passed

# 全套 unit（不需 PG）
pytest tests/unit/ -q                              # 应看到 49 passed
ruff check app/ tests/                             # All checks passed!
```

### 手工探针（可选，需 PG + 已灌 K 线数据）

```bash
uv run python -c "
from datetime import date
from app.core.db import session_scope
from app.repositories.kline_repo import KLineRepo
from app.repositories.stock_repo import StockBasicRepo
from app.repositories.trade_cal_repo import TradeCalRepo
from app.repositories.task_log_repo import TaskLogRepo
from app.services.health_day_service import get_day_detail

with session_scope() as db:
    r = get_day_detail(
        date(2024, 1, 2),
        TradeCalRepo(db), StockBasicRepo(db), KLineRepo(db), TaskLogRepo(db),
    )
    print(r)
"
```

### 通过标准

- [x] 交易日：返回 `DayDetail(day, expected_count, success_count, missing_count, error_count, missing_ts_codes[≤100], error_ts_codes[≤100], latest_task_*)`
- [x] 数据源交叉：`expected = stock_basic 活跃股`；`actual = k_line_daily 已入库`；`error = actual ∩ (trade_status!=0 AND close_raw IS NULL)`；`missing = expected - actual`；`success = actual - error`
- [x] 异常仅在**已入库行**上判定（未入库的股票只计 missing，不计 error）
- [x] 非交易日调用抛 `NotFoundError`（API 层映射 `NOT_FOUND_TRADING_DAY`）
- [x] 覆盖该日的最近 SYNC_KLINE 任务：`task_key=SYNC_KLINE:today:start:end` 解析出的 `[start,end]` 覆盖 `day` 才附加；不覆盖或 key 格式错误 → `latest_task_*` 为 `None`
- [x] Service 只读，不写 DB、不调 baostock；`pytest tests/unit/test_health_day.py` 8 passed；全套 unit 49 passed；`ruff check` 全绿

---

## 如何验收 P2-03

**目标**：确认 `run_daily_sync()` 能在**一个 baostock session** 内串行跑通四步（stock_basic → trade_cal → kline → market_cap），失败不阻塞后续、配额触顶立刻中止；APScheduler 默认关闭（`SCHEDULER_ENABLED=false`），可通过 CLI 手工触发。

### 步骤

```bash
cd backend
source .venv/bin/activate
uv sync --group dev

# 只跑本任务用例（全 mock，无网络）
pytest tests/unit/test_scheduler.py -v            # 应看到 10 passed

# 全套 unit
pytest tests/unit/ -q                              # 应看到 59 passed
ruff check app/ tests/                             # All checks passed!
```

### 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `SCHEDULER_ENABLED` | `false` | `true` 才会启动 APScheduler；本地/CI 默认关，防止意外调用 baostock |
| `SCHEDULER_HOUR` | `2` | cron hour（Asia/Shanghai） |
| `SCHEDULER_MINUTE` | `30` | cron minute |
| `SCHEDULER_TRIGGERED_BY` | `scheduler` | 写入 `data_update_task.created_by` 的标识 |

### 手工触发一次（需 PG + baostock 可达）

```bash
# 单次同步（凭一次 baostock login 跑四步）
uv run python -m app.services.scheduler
# 或
uv run python -c "from app.services.scheduler import run_daily_sync; print(run_daily_sync())"
```

预期日志：
```
DailySyncReport(today=2026-07-07,
                steps={'stock_basic':'SUCCESS','trade_cal':'SUCCESS',
                       'kline':'SUCCESS','market_cap':'SKIPPED'},
                quota_exhausted=False, errors={})
```

### 通过标准

- [x] 单进程仅一次 `baostock_session()`（避免每 step 反复 login，符合 §11.5 预算规则）
- [x] 四步串行；每步独立 try/except、独立 DB 会话；任一步失败不阻塞后续
- [x] 每步结果记录到 `DailySyncReport.steps[step] ∈ {SUCCESS, FAILED, SKIPPED}`
- [x] `AdapterQuotaExceededError` 中止后续步骤（`quota_exhausted=True`；余下 step 不出现在 `report.steps`）
- [x] `sync_kline` 非交易日 / 无活跃股 → `SKIPPED`（0 baostock 调用）
- [x] `market_cap` 仅在**季末月**（3 / 6 / 9 / 12）交易日运行；其余日 `SKIPPED`（避免每日 5000 次 profit_data）
- [x] 每步内部服务自行写 `data_update_task`（沿用 P1-05 / P1-06 已有逻辑）
- [x] `SCHEDULER_ENABLED=false`（默认）→ `build_scheduler()` 返回 None，`create_app().lifespan` 不启动 scheduler；`SCHEDULER_ENABLED=true` 才装载 cron job
- [x] `python -m app.services.scheduler` CLI 立即触发一次
- [x] `pytest tests/unit/test_scheduler.py` 10 passed；全套 unit 59 passed；`ruff check` 全绿

---

## 如何验收 P2-04

**目标**：确认 3 个新端点（K 线月历 / 单日详情 / 任务分页）全部合规 envelope、按 `prompt/reference/api_envelope.md` 分页排序、参数错误统一走 envelope（不返 422）。

### 步骤

```bash
cd backend
source .venv/bin/activate
uv sync --group dev

# 只跑本任务用例
pytest tests/unit/test_health_api_full.py -v                # 应看到 11 passed
pytest tests/integration/test_health_api_full.py -v         # 5 passed（需 PG）

# 全套 unit
pytest tests/unit/ -q                                        # 70 passed
ruff check app/ tests/                                       # All checks passed!
```

### 端点契约

| 方法 | 路径 | 参数 | 成功响应 `data` |
| --- | --- | --- | --- |
| GET | `/api/health/kline/calendar` | `year` (1990-2100), `month` (1-12) | `{year, month, days: [{date, is_open, status, expected, actual, has_anomaly}, ...]}` |
| GET | `/api/health/kline/day/{date}` | path: `YYYY-MM-DD` | `{date, expected_count, success_count, missing_count, error_count, missing_ts_codes[], error_ts_codes[], latest_task}` |
| GET | `/api/health/tasks` | `page` (≥1), `page_size` (≤200), `order_by` ∈ `{started_at, finished_at, task_type, status}`, `order` ∈ `{asc, desc}` | `{items, total, page, page_size}` |

### 错误码

| 场景 | code |
| --- | --- |
| `year/month` 越界 / 缺失必填 / 类型不对 | `VALIDATION_INVALID_PARAMETER` |
| `day` 不是 `YYYY-MM-DD` | `VALIDATION_INVALID_DATE` |
| `day` 是非交易日 | `NOT_FOUND_TRADING_DAY` |
| `page_size > 200` | `VALIDATION_PAGE_SIZE_TOO_LARGE` |
| `order_by` 不在 whitelist | `VALIDATION_INVALID_ORDER_FIELD`（`detail.allowed` 列出白名单） |
| `order` 不是 asc/desc | `VALIDATION_INVALID_ORDER` |

### 手工探针（需服务运行）

```bash
uvicorn app.main:app --port 8000 &

curl -s "http://localhost:8000/api/health/kline/calendar?year=2024&month=1" | python -m json.tool
curl -s "http://localhost:8000/api/health/kline/day/2024-01-02"          | python -m json.tool
curl -s "http://localhost:8000/api/health/kline/day/2024-01-06"          | python -m json.tool  # 周六 → NOT_FOUND_TRADING_DAY
curl -s "http://localhost:8000/api/health/tasks?page=1&page_size=5"      | python -m json.tool
curl -s "http://localhost:8000/api/health/tasks?page_size=999"           | python -m json.tool  # → VALIDATION_PAGE_SIZE_TOO_LARGE
```

### 通过标准

- [x] 3 个新端点 envelope 合规；成功返 `success=true`，业务错误返 `success=false` + `code`
- [x] 分页格式：`{items, total, page, page_size}`；`page_size` 默认 50、上限 200
- [x] 排序：whitelist（`started_at / finished_at / task_type / status`）+ `order ∈ {asc, desc}`；tie-breaker 用 `id desc` 稳定分页
- [x] `NotFoundError`（非交易日）→ 200 + `NOT_FOUND_TRADING_DAY` envelope（不是 HTTP 404）
- [x] FastAPI `Query` 校验失败（越界 / 类型错 / 缺参）被 `RequestValidationError` handler 接管，全部走 envelope
- [x] `pytest tests/unit/test_health_api_full.py` 11 passed；全套 unit 70 passed；`ruff check` 全绿

---

## 如何验收 P2-05

**目标**：确认前端脚手架就绪 —— 未登录跳 `/login`；登录后落 Dashboard 占位；所有 API 请求自动带 `X-User`；envelope 解包在拦截器统一完成；类型检查、lint、构建全绿。

### 步骤

```bash
cd frontend
npm install                 # 若尚未装依赖
npm run typecheck           # tsc --noEmit（应无输出）
npm run lint                # eslint（应无输出）
npm run build               # tsc && vite build（应看到 dist/ 产物）

npm run dev                 # 起 vite (5173)；配合后端 (uvicorn 8000)
# 打开 http://localhost:5173
```

### 通过标准

- [x] 打开 `/` 未登录 → 跳 `/login`（用户下拉 + 登录按钮）
- [x] 登录后进入 `/`，`<AppLayout>` 渲染顶栏（当前用户 + 退出）+ 侧栏（Dashboard / 数据浏览占位）+ Dashboard 占位卡
- [x] 每个 axios 请求 header 带 `X-User: <username>`（DevTools Network 可查）
- [x] envelope 拦截器：`success=true` → `res.data` 已解包为业务 payload；`success=false` → 抛 `EnvelopeError(code, message, detail)`
- [x] React Query provider + Router 装配就绪（`main.tsx`）
- [x] `authStore` 持久到 `localStorage`（`istock.auth` key）；刷新页面登录状态保留
- [x] `<AdminPasswordModal>` 组件在（供后续敏感操作使用）；`api/health.ts` 类型契约与后端 P2-04 对齐
- [x] `npm run typecheck / lint / build` 全绿

---

## 如何验收 P2-06

**目标**：确认 Dashboard 集成 4 张状态卡 + K 线月历（ECharts）+ 任务日志表；点击月历跳转单日详情；所有页面接真后端 API，无 mock。

### 步骤

```bash
cd frontend
npm install                # 若尚未装 echarts / echarts-for-react
npm run typecheck          # 应无输出
npm run lint               # 应无输出
npm run build              # 应看到 dist/index.html + assets

# 起后端 + 前端调试
cd ../backend && uvicorn app.main:app --port 8000 &
cd ../frontend && npm run dev
# 浏览器打开 http://localhost:5173，登录后进入 Dashboard
```

### 页面功能

| 区块 | 数据源 | 说明 |
| --- | --- | --- |
| 顶部 4 卡 + 任务摘要 | `GET /api/health/summary` | 每卡显示 count + last_updated；最后一栏总任务数 + 最近开始时间 |
| K 线月历 | `GET /api/health/kline/calendar?year=&month=` | 左右箭头 / DatePicker 切月；颜色：绿=完整、黄=部分、红=全缺、灰=非交易；⚠ 表示当日存在异常行；点击交易日跳 `/day/:date` |
| 单日详情页 (`/day/:date`) | `GET /api/health/kline/day/{date}` | 4 项统计（应更新/成功/缺失/异常）+ 最近任务摘要 + 缺失/异常股票 List（各 ≤100）；非交易日渲染 Alert 提示（NOT_FOUND_TRADING_DAY 已被拦截器映射为 `EnvelopeError`） |
| 任务日志表 | `GET /api/health/tasks?page=&page_size=&order_by=&order=` | 分页（20/条，可切 10/20/50/100）；排序 whitelist `started_at / finished_at / task_type / status`；status 用彩色 Tag |

### 通过标准

- [x] Dashboard 展示 4 张核心状态卡（stock_basic / trade_cal / k_line_daily / latest_market_cap）+ 最近任务摘要
- [x] K 线月历支持月份切换（DatePicker + 左右箭头）+ 4 色状态映射 + 异常 ⚠ 标记 + hover tooltip 显示 expected/actual
- [x] 点击月历某交易日跳转 `/day/:date` 单日详情页；非交易日不响应点击
- [x] 单日详情页显示 4 项统计 + 缺失/异常股票列表（各 ≤100）
- [x] 任务日志表分页 + 排序（whitelist）
- [x] **接真后端 API，React Query 缓存 + envelope 解包在 `http.ts` 拦截器完成，无 mock**
- [x] `npm run typecheck / lint / build` 全绿

---

## Phase 2 收官

- **6 / 6 任务完成**
- **数据健康**闭环打通：Service 层（P2-01 月历 / P2-02 单日）→ Scheduler（P2-03 daily job）→ API（P2-04 3 个新端点）→ 前端（P2-05 脚手架 / P2-06 Dashboard）
- **新增测试**：unit 70 passed（P2-01 9 / P2-02 8 / P2-03 10 / P2-04 11 + 现有 32）；integration 增 5（P2-04）
- **新增前端资产**：axios envelope 拦截 / Zustand persist / React Query / React Router 守卫 / 4 张状态卡 / ECharts 月历 / AntD 分页表 / 单日详情页
- **baostock 预算**：全阶段生产日常同步计约 2 万次/日；scheduler market_cap 仅季末月运行，Phase 2 未增加固定预算消耗

**下一步 → Phase 3 数据浏览**（数据表列表 / 通用表 / 字段控制 / 浏览历史 / 股票详情）

---

## Phase 1 收官

- **7 / 7 任务完成**
- 数据基座（stock_basic / trade_calendar / k_line_daily / latest_market_cap / data_update_task）就位
- baostock 单源全链路打通；市值合成方案确认可用
- API 层第一个端点 `/api/health/summary` 上线
- Alembic 迁移历史：`0001_initial` / `0002_add_latest_market_cap` / `0003_market_cap_from_baostock`
- 测试基础设施：unit 41 tests + integration 24 tests；session-scoped baostock login + 智能 skip

**下一步 → Phase 2 数据健康**（P2-01 K 线月历 → P2-06 Dashboard 前端）

---

## 文档索引
| --- | --- |
| [`PROJECT.md`](PROJECT.md) | 项目宪章：六阶段 + 硬规则 |
| [`docs/01_REQUIREMENTS.md`](docs/01_REQUIREMENTS.md) | v1 需求（能力清单 + 边界 + 术语） |
| [`docs/02_USER_STORIES.md`](docs/02_USER_STORIES.md) | 用户故事 + EARS 验收标准 |
| [`docs/03_MODULES.md`](docs/03_MODULES.md) | 前后端模块划分 + 依赖 |
| [`docs/04_TECH_STACK.md`](docs/04_TECH_STACK.md) | 技术选型 + 15 条 ADR |
| [`docs/05_DATA_MODEL.md`](docs/05_DATA_MODEL.md) | 16 张表 + DDL + 关系图 |
| [`docs/06_TASKS.md`](docs/06_TASKS.md) | 任务清单（P1-01 → P2-06 + 后续 Phase） |
| [`docs/algorithm.md`](docs/algorithm.md) | 板块动量因子算法规范 |
| [`prompt/CONTEXT.md`](prompt/CONTEXT.md) | vibe-coding 会话前置上下文 |
| [`prompt/TASK_TEMPLATE.md`](prompt/TASK_TEMPLATE.md) | 任务提交模板 |
| [`prompt/reference/`](prompt/reference/) | baostock / sw_parser / envelope cheatsheet |

---

## 部署步骤

**当前状态：占位**。生产部署方案将在 Phase 6 之后完善（当前 v1 优先本地开发与 Docker 单机部署）。

预期形态：

```
[user] ──HTTPS──> [nginx]
                    │
                    ├──/──────> frontend 静态资源（Vite build 产物）
                    └──/api──> backend uvicorn (Docker)
                                    │
                                    └──> PostgreSQL 15 (Docker + 数据卷)
```

**待补内容**（TODO）：
- [ ] nginx 反向代理配置样例
- [ ] `docker-compose.prod.yml`（生产参数：环境变量注入 / 无 mount / 前端预构建）
- [ ] PG 备份策略（`pg_dump` cron + 保留 30 天）
- [ ] 日志采集方案
- [ ] CI/CD 流程（GitHub Actions / 智研）
- [ ] 秘钥管理（`ADMIN_PASSWORD_HASH` 等敏感配置）

**关联文档**：`docs/04_TECH_STACK.md §10`（部署与本地开发）。

---

## 目录结构

```
istock/
├── PROJECT.md                        # 宪章
├── README.md                         # 本文件
├── docker-compose.yml                # 一键起 postgres + backend + frontend
│
├── docs/                             # 5 份主文档 + 任务清单 + 算法
│   ├── 01_REQUIREMENTS.md
│   ├── 02_USER_STORIES.md
│   ├── 03_MODULES.md
│   ├── 04_TECH_STACK.md
│   ├── 05_DATA_MODEL.md
│   ├── 06_TASKS.md
│   └── algorithm.md
│
├── prompt/                           # vibe-coding 会话上下文
│   ├── CONTEXT.md
│   ├── TASK_TEMPLATE.md
│   └── reference/
│       ├── baostock_cheatsheet.md
│       ├── sw_parser_cheatsheet.md
│       ├── api_envelope.md
│       └── _archive/                 # 归档的旧 prompt
│
├── sw-data/                          # 申万样例数据（开发期用）
│
├── backend/
│   ├── pyproject.toml                # uv 管理
│   ├── uv.lock                       # 锁文件
│   ├── Dockerfile
│   ├── .env.example
│   ├── app/
│   │   ├── main.py                   # FastAPI 组装
│   │   ├── api/                      # 路由（每领域一个文件）
│   │   ├── services/                 # 业务编排
│   │   ├── repositories/             # 数据访问
│   │   ├── adapters/
│   │   │   ├── baostock_adapter.py   # 主 adapter (P1-03)
│   │   │   ├── baostock_profit.py    # profit_data 供市值合成 (P1-04)
│   │   │   ├── baostock_types.py     # DTO 集中处
│   │   │   └── sw_parser/            # 6 子文件（Phase 4）
│   │   ├── factors/                  # 6 子文件（Phase 5）
│   │   ├── core/                     # config / envelope / db / deps / errors
│   │   └── models/                   # SQLAlchemy models（P1-02 起）
│   ├── alembic/                      # (P1-02 起)
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── Dockerfile
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/
        ├── pages/
        ├── components/
        ├── store/
        └── utils/
```
