# istock

面向少量用户的 A 股量化分析 Web 系统，定位为“数据基座 + 分析工具”。系统用于维护共享的 A 股基础数据，并提供数据健康检查、数据浏览、股票详情、申万行业分类和板块动量因子分析。

本项目不提供交易功能，也不处理实时行情。

## 开发者快速开始

### 环境要求

| 工具 | 版本 |
| --- | --- |
| Python | ≥ 3.11 |
| uv | 最新稳定版 |
| Node.js | ≥ 20 LTS |
| PostgreSQL | ≥ 15 |

项目采用原生运行方式，不依赖容器环境。

### 1. 准备 PostgreSQL

macOS 可通过 Homebrew 安装：

```bash
brew install postgresql@15
brew link --force postgresql@15
brew services start postgresql@15
```

首次使用时创建开发数据库：

```bash
createuser istock
createdb -O istock istock
psql -d postgres -c "ALTER USER istock WITH PASSWORD 'istock';"
```

默认连接地址：

```text
postgresql+psycopg://istock:istock@localhost:5432/istock
```

如果数据库位于其他主机，请在后端环境变量中修改 `DATABASE_URL`。

### 2. 初始化后端

```bash
cd backend
cp .env.example .env
uv sync --group dev
set -a && source .env && set +a
uv run alembic upgrade head
```

> 当前 `0007_raw_kline_qfq_cache` 迁移会清空既有行情、复权因子、市值快照和因子结果，以便按新结构重新初始化；执行前请确认无需保留这些数据。

需要从 Tushare 同步数据时，在 `backend/.env` 中配置：

```env
TUSHARE_TOKEN=<your-token>
```

### 3. 初始化前端

```bash
cd frontend
cp .env.example .env
npm install
```

默认情况下，Vite 会将 `/api` 请求代理到 `http://localhost:8000`。后端位于其他地址时，可修改：

```env
VITE_API_TARGET=http://localhost:8000
```

### 4. 启动开发环境

打开两个终端。

后端：

```bash
cd backend
set -a && source .env && set +a
uv run uvicorn app.main:app --reload --port 8000
```

前端：

```bash
cd frontend
npm run dev
```

服务地址：

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:5173 |
| 健康检查 | http://localhost:8000/api/health |
| OpenAPI 文档 | http://localhost:8000/api/docs |

## 数据初始化与更新

以下命令均在 `backend/` 目录运行，并要求正确配置 `DATABASE_URL` 和 `TUSHARE_TOKEN`。

初始化指定日期范围的数据：

```bash
uv run python -m app.data_service init \
  --start 2026-05-08 \
  --end 2026-07-08
```

初始化会逐交易日提交并输出进度；重复执行默认跳过已成功日期。需要强制重抓时增加 `--force`。

更新指定交易日：

```bash
uv run python -m app.data_service update --date 2026-07-08
```

其他数据服务命令：

```bash
# 同步股票基础信息
uv run python -m app.data_service sync-basic

# 同步交易日历
uv run python -m app.data_service sync-calendar \
  --start 2020-01-01 \
  --end 2026-12-31

# 重建全市场最新前复权展示缓存
uv run python -m app.data_service rebuild-qfq-cache

# 只重建指定股票（参数可重复）
uv run python -m app.data_service rebuild-qfq-cache --ts-code 600000.SH
```

完整说明见 [`backend/scripts/README.md`](backend/scripts/README.md)。

## 常用开发命令

### 后端

在 `backend/` 目录执行：

| 用途 | 命令 |
| --- | --- |
| 安装依赖 | `uv sync --group dev` |
| 启动开发服务 | `uv run uvicorn app.main:app --reload --port 8000` |
| 数据库迁移 | `uv run alembic upgrade head` |
| 全部测试 | `uv run pytest` |
| 单元测试 | `uv run pytest -m "not integration"` |
| 集成测试 | `uv run pytest -m integration` |
| 代码检查 | `uv run ruff check app/ tests/` |
| 自动修复 | `uv run ruff check --fix app/ tests/` |
| 类型检查 | `uv run mypy app/` |

集成测试需要可访问的 PostgreSQL；部分测试还需要外部数据源。

### 前端

在 `frontend/` 目录执行：

| 用途 | 命令 |
| --- | --- |
| 安装依赖 | `npm install` |
| 启动开发服务 | `npm run dev` |
| 类型检查 | `npm run typecheck` |
| 代码检查 | `npm run lint` |
| 生产构建 | `npm run build` |
| 预览构建产物 | `npm run preview` |

## 项目说明

### 技术栈

- 前端：React 18、TypeScript、Vite 5、Ant Design 5、TanStack Query
- 后端：FastAPI、SQLAlchemy 2.x、Alembic、APScheduler
- 数据库：PostgreSQL 15+
- 数据源：Tushare Pro；保留部分 Baostock legacy 能力
- 包管理：后端使用 uv，前端使用 npm

### 系统架构

```text
React + Vite
      │
      │ REST API
      ▼
FastAPI
      ├── api           HTTP 接口与参数校验
      ├── services      业务编排与事务边界
      ├── repositories  数据访问
      ├── adapters      外部数据源适配
      ├── data_service  初始化、增量更新与 QFQ 缓存
      ├── factors       板块动量因子
      └── core          配置、数据库和统一响应
      │
      ▼
PostgreSQL
```

API 使用统一响应结构：

```json
{
  "success": true,
  "data": {},
  "message": ""
}
```

### 功能边界

系统当前面向单机、少并发场景，主要能力包括：

- 股票基础信息、交易日历和日 K 线维护
- 数据更新任务与完整性检查
- 数据表浏览和股票详情
- 申万行业分类查询与同步
- 板块动量因子配置、计算和结果查询

项目明确不包含：

- 证券交易与订单管理
- 实时行情
- 高频或大规模并发服务
- 页面直接访问数据库或计算因子

### 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── adapters/
│   │   ├── api/
│   │   ├── core/
│   │   ├── data_service/
│   │   ├── factors/
│   │   ├── models/
│   │   ├── repositories/
│   │   └── services/
│   ├── alembic/
│   ├── scripts/
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/
│       ├── components/
│       ├── pages/
│       └── store/
├── docs/
└── prompt/
```

### 开发约定

- 页面仅通过公开 API 获取数据。
- API 不直接访问 Repository，由 Service 负责业务编排。
- Adapter 只访问外部数据源，不写数据库。
- 数据库结构变更必须通过 Alembic。
- 后端依赖变更需更新 `pyproject.toml` 和 `uv.lock`。
- 前端依赖变更需更新 `package.json` 和 `package-lock.json`。
- 提交前运行对应测试、Lint 和类型检查。

## 开发进度

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Phase 1 | 数据基座：基础表、数据源适配、同步服务、健康 API | ✅ 完成 |
| Phase 2 | 数据健康：月历、单日详情、定时任务、Dashboard | ✅ 完成 |
| Phase 3 | 数据浏览：表浏览、筛选、历史记录、股票详情 | ✅ 完成 |
| Phase 4 | 申万行业分类查询、Tushare 同步与定时更新 | ✅ 完成 |
| Phase 5 | 板块动量因子 | ✅ 完成 |
| Phase 6 | 用户、日志、交互与部署完善 | ⏳ 待完成 |

更细的任务状态和验收定义见 [`docs/06_TASKS.md`](docs/06_TASKS.md)。

## 部署现状

目前仓库以本地开发为主，尚未提供完整的生产部署脚本。预期生产结构为：

```text
用户
  │
  ▼
nginx
  ├── /     → frontend/dist
  └── /api  → FastAPI（systemd / supervisor）
                    │
                    └── PostgreSQL
```

正式上线前仍需补充：

- nginx 配置与 HTTPS
- 后端进程管理配置
- 环境变量和密钥管理
- 数据库备份与恢复
- 日志轮转和监控
- CI/CD 发布及回滚流程

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [`PROJECT.md`](PROJECT.md) | 项目目标、阶段和开发原则 |
| [`docs/01_REQUIREMENTS.md`](docs/01_REQUIREMENTS.md) | 需求与系统边界 |
| [`docs/02_USER_STORIES.md`](docs/02_USER_STORIES.md) | 用户故事和验收标准 |
| [`docs/03_MODULES.md`](docs/03_MODULES.md) | 模块划分与依赖关系 |
| [`docs/04_TECH_STACK.md`](docs/04_TECH_STACK.md) | 技术选型和架构决策 |
| [`docs/05_DATA_MODEL.md`](docs/05_DATA_MODEL.md) | 数据模型和表结构 |
| [`docs/06_TASKS.md`](docs/06_TASKS.md) | 开发任务和进度 |
| [`docs/algorithm.md`](docs/algorithm.md) | 板块动量因子算法 |
| [`常用命令.md`](常用命令.md) | PostgreSQL 运维和排错命令 |
