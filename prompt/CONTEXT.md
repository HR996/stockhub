# istock — vibe-coding 会话前置上下文

> 每次向 AI 提交任务时，本文件全文作为 prompt 前置。
> **保持精简**：只放"每次都需要的" —— 具体细节走文档路径引用。

---

## 项目一句话

istock v1 是面向少量用户的 A 股量化分析 Web 系统：数据基座 + 数据健康 + 数据浏览 + 股票详情 + 申万分类维护 + 板块动量因子。

## 技术栈（锁定）

**后端**：Python 3.11+ / **uv** 包管理（`uv.lock` 提交入库） / FastAPI / SQLAlchemy 2.x / Alembic / Pydantic v2 / APScheduler / pytest / Ruff / mypy

**数据库**：**PostgreSQL 15+**（不用 SQLite / DuckDB / MySQL）

**数据源**：
- baostock（**唯一数据源**）—— 股票基础信息、交易日历、K 线（含 tradestatus / isST）、季度财报（`query_profit_data` 获取 totalShare 用于合成最新市值）
- **最新市值合成**：`totalShare × close_raw`（详见 `04_TECH_STACK §4.2` / ADR-16）

**前端**：TypeScript 5 / React 18 / Vite 5 / Ant Design 5 / Zustand / @tanstack/react-query / axios / lightweight-charts / ECharts

**申万解析**：`rarfile` + 系统 `unrar` / `openpyxl`（xlsx）/ `xlrd==1.2.0`（xls，锁死版本）

## 五条硬规则（PROJECT.md §2）

1. **MVP 优先** — 每阶段可运行，禁止一次实现全部
2. **数据优先** — 业务建立在统一数据基座上，先做数据后做业务
3. **API First** — 所有页面通过 REST API 拿数据，前端不得直连 DB
4. **前后端解耦** — 后端只做数据 + 因子 + 状态；前端只做展示 + 输入
5. **单文件 <500 行** — 超限必须按子模块拆分（sw_parser / factors 已预拆）

## baostock 调用预算（硬约束，PROJECT.md §11.5）

**5 万次 / 日**（超限当日无法恢复）。生产日常约 2 万 / 日，剩余 3 万供开发+测试。

必守：
- **不按日循环 K 线** — `fetch_kline` 传区间，一次多天；禁 `for day in days: fetch(day, day)`
- **单元测试禁真接口** — `tests/unit/**` 一律 mock `bs.query_*` / `fetch_*`
- **集成测试样本上限** — 默认 ≤ 20 支 × ≤ 10 交易日；全市场用例每 pytest run **只能一次**，且不重跑
- **登录复用** — `bs_session` session-scope 已生效，禁止在循环里反复 login/logout
- **触顶（`error_code=10001007`）立即中止** — 写 FAILED，不继续消耗
- **改动 adapter/services/sync_* 前先估算调用增量**；单次 pytest 预计 > 200 次真调用必须先改 mock

## 分层依赖（禁止越权）

```
Router → Service → Repository → Database
                → Adapter → 外部
                → Factor → Repository（只读）
```

- Adapter **不写 DB**
- Repository **不调外部**
- Factor **不调 Adapter，不直连 DB**
- API 层**不含业务逻辑**（只做参数校验 + 错误映射 + 响应包装）

## 目录布局

```
backend/app/
├── api/          # 路由（每领域一个文件）
├── services/     # 业务编排 + 事务边界
├── repositories/ # 数据访问（返回领域方法，不返回 ORM Query）
├── adapters/
│   ├── baostock_adapter.py     # 主 adapter
│   ├── baostock_profit.py      # profit_data（供市值合成）
│   ├── baostock_types.py       # DTO
│   └── sw_parser/     # 6 个子文件（archive_reader / excel_parser / taxonomy_builder / member_builder / validator / preview_builder）
├── factors/      # 6 个子文件（filters / returns / top_selection / aggregation / scoring / runner）
├── core/         # config / db / deps / envelope / errors / logging
└── main.py

frontend/src/
├── api/          # 与后端 api/ 一一对应
├── pages/
├── components/
├── store/
└── main.tsx
```

## API 契约

**响应 envelope**（无一例外）：
```json
{ "success": true, "data": {}, "message": "" }
```

**认证 header**：
- `X-User: <username>` — 每次请求都带
- `X-Admin-Password: <sha256>` — 敏感操作追加

**分页**：`?page=1&page_size=50`；响应 `data` 含 `items / total / page / page_size`

**排序**：`?order_by=trade_date&order=desc`

**错误码前缀**：`AUTH_* / VALIDATION_* / NOT_FOUND_* / CONFLICT_* / ADAPTER_* / PARSER_* / INTERNAL_*`

**时间格式**：ISO 8601 + `Asia/Shanghai`；纯日期用 `YYYY-MM-DD`

## 编码规约

- **不写多行注释**；只在"WHY 非显然"时写单行说明
- **不写 backwards-compat 兼容层**
- **不加防御性错误处理**（内部代码信任框架 / 类型系统；只在 boundary 校验）
- **不为假设的未来需求做设计**
- **Repository 幂等 upsert**（PG `INSERT ... ON CONFLICT DO UPDATE`）
- **写操作强制记 `X-User`**（audit_log）

## 关键坑（记忆点）

- baostock adjustflag：`1=后复权 / 2=前复权 / 3=不复权`；因子用 **2**
- baostock 停牌日返回空价格 → `trade_status=0` + 价格 null
- xls 必须用 `xlrd==1.2.0`；2.0+ 已移除 xls 支持
- rar 解压需在操作系统安装 `unrar`（不是 pip 依赖）
- 申万版本 `is_current` 用 PG 部分唯一索引保证同时只有一个当前版本
- K 线三口径存**一表 3 组字段**（不拆 3 张表）

## 文档引用

不要把文档全文粘进 prompt。每个任务只 `Read: docs/NN_*.md#锚点`：

- `docs/01_REQUIREMENTS.md` — 系统能力清单（`§3.x.y` 编号引用）
- `docs/02_USER_STORIES.md` — 用户故事 + EARS 验收标准（`US-x.y` 引用）
- `docs/03_MODULES.md` — 模块划分与依赖
- `docs/04_TECH_STACK.md` — 技术选型 + ADR 索引
- `docs/05_DATA_MODEL.md` — 表结构 + 字段说明 + DDL
- `docs/algorithm.md` — 板块动量因子算法（后续可能迁入 05）
- `docs/06_TASKS.md` — 任务清单（本轮任务的 ID 定义）
- `PROJECT.md` — 项目宪章（六阶段 + 硬规则）
- `prompt/reference/*.md` — baostock / sw_parser / envelope cheatsheet
