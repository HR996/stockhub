# istock v1 功能板块设计

> ⚠️ **申万模块设计已更新**（2026-07-08）：`app/adapters/sw_parser/` 六子模块方案作废；申万分类改由 `app/adapters/tushare_adapter.py` 直接调用 Tushare Pro `index_classify` / `index_member_all` 获取，服务入口为 `app/services/sw_sync_service.py`。管理员上传/预览/确认/回滚流程移除，代之以只读查询 API `/api/industry/{tree,stock/:ts,last-sync}` 与 APScheduler 每周同步任务（`SCHEDULER_SW_ENABLED=true` 启用）。详见 `prompt/reference/tushare_sw_cheatsheet.md` 与 `CLAUDE.md`。以下文本仅保留作为历史设计存档。

> 本文档描述系统的**模块划分、职责边界、模块依赖、模块 ↔ 用户故事映射**。
> 具体的技术选型（框架、库、版本）见 `docs/04_TECH_STACK.md`。
> 具体的表结构与 DDL 见 `docs/05_DATA_MODEL.md`。
> 用户故事编号见 `docs/02_USER_STORIES.md`。

---

## 1. 分层原则（复述 PROJECT.md §2 核心约束）

- **API First**：所有页面通过 REST API 获取数据；前端不得直接访问数据库
- **前后端解耦**：后端只做数据维护 / 查询 / 因子计算 / 状态管理；前端只做展示 / 输入 / 交互
- **单文件 500 行硬约束**：所有源码文件不超过 500 行，超限时按子模块预拆
- **禁止**：巨型 Service、巨型 Controller、页面直接拼 SQL、页面直接计算因子

---

## 2. 后端模块图

```
                         ┌────────────────────────────────┐
                         │         API / Router           │
                         │  (FastAPI 路由 + 请求校验)     │
                         └──────────────┬─────────────────┘
                                        │
                         ┌──────────────▼─────────────────┐
                         │            Service             │
                         │  (业务编排 / 事务边界 / 权限)  │
                         └──────────────┬─────────────────┘
                                        │
                    ┌───────────────────┼──────────────────┐
                    │                   │                  │
       ┌────────────▼────────┐  ┌───────▼────────┐  ┌──────▼──────┐
       │     Repository      │  │    Adapter     │  │   Factor    │
       │ (数据表 CRUD /查询) │  │ (外部数据源)   │  │  (因子计算) │
       └────────────┬────────┘  └───────┬────────┘  └──────┬──────┘
                    │                   │                  │
                    ▼                   ▼                  ▼
              ┌──────────┐        ┌──────────┐       ┌──────────┐
              │ Database │        │ baostock │       │ Repository│
              │          │        │ akshare  │       │  (只读)  │
              │          │        │ SW-Parser│       │          │
              └──────────┘        └──────────┘       └──────────┘
```

**关键约束**：

- **Adapter 只对外**（外部数据源、文件解析），不写数据库
- **Repository 只对内**（数据表 CRUD），不调外部服务
- **Service 是唯一编排层**，跨 Repository / Adapter / Factor 的组合都在这里完成
- **Factor 只依赖 Repository**，不直接访问 Database，不调 Adapter
- **API 层不包含业务逻辑**，只做 HTTP 层的参数校验、错误映射、响应包装

---

## 3. 后端模块清单

### 3.1 API 层 `backend/app/api/`

| 模块 | 职责 | 关联用户故事 |
| --- | --- | --- |
| `auth.py` | 登录 / 用户名校验 / 敏感操作密码校验 | US-1.1、US-1.2、US-1.4 |
| `health.py` | 数据健康总览 / K 线月历 / 单日详情 / 任务日志 | US-3.1 ~ US-3.4 |
| `browse.py` | 数据表列表 / 表内容浏览 / 字段说明 | US-4.1、US-4.2 |
| `browse_history.py` | 浏览历史增删查 | US-4.3 |
| `stock.py` | 股票详情 / K 线查询 | US-5.1、US-5.2 |
| `industry.py` | 申万分类查询 / 版本列表 / 上传 / 预览 / 写入 / 回滚 | US-6.1 ~ US-6.6 |
| `factor.py` | 因子计算 / 结果查询 / **板块下钻** / **板块股票列表** / 配置增删查改 | US-7.1 ~ US-7.8 |
| `admin.py` | 异常日志查看 / 添加用户 | US-8.1、US-9.1 |

**约束**：

- 每个文件只放一个领域的路由，不允许跨领域
- 所有响应遵循统一 envelope `{success, data, message}`
- 敏感操作在路由入口通过依赖注入触发密码校验
- **文件超过 400 行**（预警线）时提前按子路径拆分（如 `industry_upload.py` / `industry_rollback.py`）

### 3.2 Service 层 `backend/app/services/`

| 模块 | 职责 | 关联用户故事 |
| --- | --- | --- |
| `auth_service.py` | 登录校验、会话管理、敏感操作密码校验、日志写入 | US-1.1 ~ US-1.4 |
| `sync_basic_service.py` | 股票基础信息 / 交易日历同步的编排 | US-2.1 |
| `sync_kline_service.py` | Legacy Baostock 未复权 K 线同步 | US-2.1、US-2.2、US-2.3 |
| `sync_market_cap_service.py` | 最新市值同步（走 akshare 兜底） | US-2.4 |
| `health_service.py` | 数据健康状态计算（表状态、月历、单日详情） | US-3.1 ~ US-3.4 |
| `browse_service.py` | 表数据浏览的分页 / 排序 / 筛选逻辑 | US-4.1、US-4.2 |
| `browse_history_service.py` | 浏览历史保存与恢复 | US-4.3 |
| `stock_service.py` | 股票详情聚合（跨基础信息 + 行业 + K 线） | US-5.1、US-5.2 |
| `industry_service.py` | 申万分类查询、版本管理、上传编排、回滚编排 | US-6.1 ~ US-6.6 |
| `factor_service.py` | 因子计算编排（调用 Factor 子模块）+ 配置管理 + 失效标记 + **板块下钻查询** + **板块股票列表查询** | US-7.1 ~ US-7.8 |
| `admin_service.py` | 异常日志查询、添加用户 | US-8.1、US-9.1 |
| `scheduler.py` | 后台定时任务定义（每日同步 stock_basic / trade_cal / kline / market_cap） | US-2.1、US-3.4 |

**约束**：

- Service 只编排，不写 SQL，不解析文件
- 事务边界在 Service 层（跨 Repository 时用一个 UOW）
- 需要审计的操作在 Service 层写日志（`X-User` 从上下文取，不从参数取）

### 3.3 Repository 层 `backend/app/repositories/`

| 模块 | 职责 | 对应主表 |
| --- | --- | --- |
| `stock_repo.py` | 股票基础信息 CRUD | `stock_basic` |
| `trade_cal_repo.py` | 交易日历 CRUD、按 window 回溯交易日 | `trade_calendar` |
| `kline_repo.py` | K 线 CRUD、区间查询、健康统计 | `k_line_daily` |
| `market_cap_repo.py` | 最新市值 CRUD | `latest_market_cap` |
| `industry_repo.py` | 申万分类树 / 成分表 CRUD、按版本查询 | `sw_index_classify`、`sw_index_member_all` |
| `industry_version_repo.py` | 申万版本快照管理 | `sw_industry_version` |
| `csrc_industry_repo.py` | 证监会行业分类 CRUD | `csrc_industry` |
| `task_log_repo.py` | 数据更新任务日志 | `data_update_task` |
| `factor_result_repo.py` | 因子结果 CRUD、失效标记 | `factor_result` |
| `factor_config_repo.py` | 因子配置 CRUD | `factor_config` |
| `browse_history_repo.py` | 浏览历史 CRUD | `browse_history` |
| `user_repo.py` | 预配置用户名 / 添加用户 | `user_account` |
| `error_log_repo.py` | 异常日志 CRUD | `error_log` |
| `audit_log_repo.py` | 关键操作审计日志 | `audit_log` |

**约束**：

- Repository 提供的都是**领域方法**（如 `find_missing_stocks_on_date`），不暴露原始 ORM Query
- 幂等 upsert 在 Repository 层实现（Service 只负责调用）

### 3.4 Adapter 层 `backend/app/adapters/`

**核心：只对外部数据源与文件解析，不写数据库**

| 模块 | 职责 | 关联用户故事 |
| --- | --- | --- |
| `baostock_adapter.py` | baostock login/logout context、股票基础信息、交易日历、K 线、`tradestatus`、`isST` | US-2.1 ~ US-2.3 |
| `akshare_adapter.py` | akshare 最新市值获取（`stock_zh_a_spot_em`） | US-2.4 |
| `sw_parser/` | 申万压缩包解析（子模块，见 §3.5） | US-6.2、US-6.3 |

**约束**：

- Adapter 返回**纯数据结构**（Pydantic model / dataclass），不返回 ORM 对象
- Adapter 内不做业务判断（合法性校验放到 Service 层）
- 外部服务失败时抛出**分类明确的异常**（`AdapterConnectionError` / `AdapterDataError` / `AdapterAuthError`）

### 3.5 SW-Parser 子模块 `backend/app/adapters/sw_parser/`

**独立列出：因申万解析器结构复杂，且极易超过 500 行硬约束**

| 子模块 | 职责 |
| --- | --- |
| `archive_reader.py` | 压缩包抽取（rar 走 `rarfile` + 系统 `unrar`；zip 走 stdlib `zipfile`），返回临时目录内的文件清单 |
| `excel_parser.py` | xls 走 `xlrd==1.2.0`，xlsx 走 `openpyxl`，pandas 统一入口，返回 DataFrame |
| `taxonomy_builder.py` | 从 DataFrame 构造分类树（对齐 TuShare `index_classify`：`index_code` / `industry_name` / `level` / `industry_code` / `is_pub` / `parent_code` / `src`） |
| `member_builder.py` | 从 DataFrame 构造成分构成表（对齐 TuShare `index_member_all`：`l1_code` / `l1_name` / `l2_code` / `l2_name` / `l3_code` / `l3_name` / `ts_code` / `name` / `in_date` / `out_date` / `is_new`） |
| `validator.py` | 校验：格式、字段、行业层级、股票代码；返回结构化错误清单 |
| `preview_builder.py` | 生成写入影响预览：新增 / 删除 / 变更计数与明细 |

**约束**：

- 每个子文件严格 <300 行，为将来拓展留出余量
- `archive_reader` 与 `excel_parser` 应可独立单元测试（不依赖真实压缩包，用 fixture）
- Parser 全流程只读，不改数据库；写入由 `industry_service` 调用 Repository 完成

### 3.6 Factor 子模块 `backend/app/factors/`

**独立列出：因子服务的算法体量单文件必然超限**

| 子模块 | 职责 | 引用 |
| --- | --- | --- |
| `filters.py` | 股票池过滤（剔除 ST / 北交所 / 小市值 / 上市天数不足 / 名称含"指数"） | algorithm.md §4 |
| `returns.py` | 个股收益计算（simple / log），处理复权价缺失 | algorithm.md §6 |
| `top_selection.py` | 全市场 Top 集合选择 | algorithm.md §7 |
| `aggregation.py` | **多层级板块聚合**：一次输入产出 L1/L2/L3 三层的 sector 聚合数据（sector_stock_count / sector_top_stock_count / top_density / median_return），每行携带 `level` 与 `parent_sector_code` 供下钻 | algorithm.md §8、§13 |
| `scoring.py` | 板块评分（median_return_score / top_count_score）+ 小样本标记 | algorithm.md §9、§10 |
| `runner.py` | 编排入口：接收参数 → 调 Repository 拉数据 → 依次调用上述模块 → 返回**跨层级完整结果集** | algorithm.md §12 伪代码 |

**约束**：

- Factor 模块**只依赖 Repository（只读）**，绝不调 Adapter，绝不直连数据库
- `runner.py` 是唯一对 Service 暴露的入口
- 参数配置的合法性校验在 Service 层完成，Factor 内部假设参数已合法
- **多层级一次算尽**：SW 一次调用产出 L1/L2/L3 全部结果；CSRC 一次调用产出 L1；不做"按需展开"

### 3.6.1 板块下钻查询（Service 层，非 Factor 层）

因子结果的**下钻查询**属于查询逻辑，不重新计算。放在 `factor_service.py` 的下钻方法中，直接查 `factor_result_row`：

- `get_children_sectors(result_id, parent_sector_code)` — 返回该父板块下一级的板块结果集
- `get_sector_stocks(result_id, sector_code, level)` — 返回该板块的股票收益列表（按收益降序）

### 3.7 通用基础设施 `backend/app/core/`

| 模块 | 职责 |
| --- | --- |
| `config.py` | 读取配置文件（预配置用户名列表、管理员密码 hash、DB 连接串、数据源开关等） |
| `db.py` | DB 引擎、Session 管理、UOW（Unit of Work） |
| `deps.py` | FastAPI 依赖：`get_current_user`、`require_admin_password`、`get_db_session` |
| `envelope.py` | 统一响应包装 `{success, data, message}` + 分页 / 排序 / 错误码约定 |
| `errors.py` | 领域异常类（`ValidationError` / `NotFoundError` / `ConflictError` / `AdapterError` 等） |
| `logging.py` | 审计日志与异常日志的统一写入接口 |

---

## 4. 前端模块图

```
┌─────────────────────────────────────────────────┐
│                    Pages                         │
│  (dashboard / browse / stock / industry /        │
│   factor / admin / login)                        │
└─────────────────────┬───────────────────────────┘
                      │
      ┌───────────────┴────────────────┐
      │                                │
┌─────▼──────┐                 ┌──────▼──────┐
│ Components │                 │    Store    │
│ (UI 组件)  │                 │  (状态管理) │
└─────┬──────┘                 └──────┬──────┘
      │                                │
      └────────────┬───────────────────┘
                   │
              ┌────▼────┐
              │   API   │
              │ Client  │
              └────┬────┘
                   │
              ┌────▼────┐
              │  axios  │
              │(拦截器) │
              └─────────┘
```

## 5. 前端模块清单

### 5.1 页面 `frontend/src/pages/`

| 页面 | 职责 | 关联用户故事 |
| --- | --- | --- |
| `LoginPage` | 用户名登录 | US-1.1、US-1.2 |
| `DashboardPage` | 数据健康总览 + K 线月历 + 任务日志 | US-3.1 ~ US-3.4 |
| `KlineDayDetailPage` | K 线单日健康详情 | US-3.3 |
| `BrowseListPage` | 数据表列表 | US-4.1 |
| `BrowseTablePage` | 表内容浏览（分页 / 排序 / 筛选 / 字段控制） | US-4.2、US-4.3 |
| `StockDetailPage` | 股票详情（基础信息 + 行业 + K 线） | US-5.1、US-5.2 |
| `IndustryPage` | 申万分类维护（下载指引 / 上传 / 预览 / 版本 / 回滚） | US-6.1 ~ US-6.6 |
| `FactorPage` | 因子参数配置 + 计算 + 结果表（默认层级） + 面包屑容器 | US-7.1 ~ US-7.3、US-7.6 |
| `FactorDrilldownPanel` | 板块下钻结果表（子层级动量） | US-7.4 |
| `SectorStocksPanel` | 板块股票列表（默认按收益率降序） | US-7.5 |
| `FactorConfigPage` | 因子配置管理（重命名 / 复制 / 删除） | US-7.7 |
| `ErrorLogPage` | 异常日志查看 | US-8.1 |
| `UserManagePage` | 添加用户 | US-9.1 |
| `HistoryPage` | 浏览历史管理 | US-4.3 |

### 5.2 组件 `frontend/src/components/`

| 组件 | 职责 | 复用范围 |
| --- | --- | --- |
| `AppLayout` | 全局布局（顶栏 + 侧栏 + 内容区） | 全站 |
| `AdminPasswordModal` | 敏感操作密码弹窗 | 敏感操作触发点 |
| `DataTable` | 通用可控字段表格（分页 / 排序 / 筛选 / 字段显示 / 顺序拖拽） | 数据浏览 / 因子结果 |
| `KlineCalendar` | K 线月历热力组件 | Dashboard |
| `KlineChart` | K 线图组件 | 股票详情 |
| `IndustryTree` | 申万分类树展示 | 股票详情 / 分类维护 |
| `UploadPreview` | 上传影响预览组件 | 分类维护 |
| `VersionList` | 版本快照列表 + 回滚触发点 | 分类维护 |
| `ParamPanel` | 因子参数配置面板 | 因子分析 |
| `FactorBreadcrumb` | 因子下钻面包屑（会话内存活；节点删除 / 清空 / 快速跳转） | 因子分析（跨 FactorPage / 下钻面板 / 板块股票 / 个股详情） |
| `EnvelopeError` | 统一错误提示 | 全站 |

### 5.3 API Client `frontend/src/api/`

**每个后端 API 模块对应一个 Client 文件**：

| 文件 | 对应后端 |
| --- | --- |
| `auth.ts` | `api/auth.py` |
| `health.ts` | `api/health.py` |
| `browse.ts` | `api/browse.py` |
| `stock.ts` | `api/stock.py` |
| `industry.ts` | `api/industry.py` |
| `factor.ts` | `api/factor.py` |
| `admin.ts` | `api/admin.py` |
| `browseHistory.ts` | `api/browse_history.py` |

**约束**：

- 全部使用 axios 拦截器统一处理：`X-User` header、`{success, data, message}` 解包、错误 toast
- 类型定义与后端 Pydantic 模型手工对齐（v1 不引入 openapi codegen）

### 5.4 Store `frontend/src/store/`

| Store | 职责 |
| --- | --- |
| `authStore` | 当前用户名、登录状态 |
| `browseHistoryStore` | 浏览历史（本地 + 服务端同步） |
| `factorBreadcrumbStore` | 因子下钻面包屑（**仅当前会话**：内存 zustand，页面刷新即丢；节点包含类型 / 参数 / 展示标题） |
| `factorConfigStore` | 因子配置的本地缓存 |
| `industryVersionStore` | 当前申万版本号（用于失效提示） |

---

## 6. 模块依赖规则

**允许的依赖方向（单向、无环）**：

```
Router → Service → Repository → Database
                → Adapter → 外部
                → Factor → Repository（只读）
```

**禁止**：

- Repository → Service / Adapter（下层不得反向依赖上层）
- Adapter → Repository（Adapter 完全不写库）
- Factor → Adapter / Database（Factor 只走 Repository）
- API → Repository（API 必须走 Service）

**跨领域调用**：只允许经过 Service 层，禁止 Service 之间直接嵌套调用（若必要，抽公共 Service 或提取到 Repository）。

---

## 7. 模块 ↔ 用户故事映射（逆向索引）

| 用户故事 | 主要涉及模块 |
| --- | --- |
| US-1.1 用户名登录 | `api/auth`、`services/auth_service`、`repositories/user_repo`、前端 `LoginPage` |
| US-1.2 登录状态保持 | `api/auth`、前端 `authStore` |
| US-1.3 关键操作日志 | `core/logging`、`repositories/audit_log_repo` |
| US-1.4 敏感操作密码 | `api/auth`、`services/auth_service`、`AdminPasswordModal` |
| US-2.1 后台自动更新 | `services/scheduler`、`sync_basic_service`、`sync_kline_service`、`sync_market_cap_service`、`adapters/baostock_adapter`、`adapters/akshare_adapter` |
| US-2.2 动态复权 | `data_service`、`stock_adj_factor`、`qfq_cache_repo` |
| US-2.3 3 年留存 | `sync_kline_service`、`kline_repo` |
| US-2.4 最新市值 | `sync_market_cap_service`、`akshare_adapter`、`market_cap_repo` |
| US-3.1 状态总览 | `api/health`、`health_service`、多个 repo 的状态查询 |
| US-3.2 K 线月历 | `health_service`、`kline_repo`、前端 `KlineCalendar` |
| US-3.3 单日详情 | `health_service`、`kline_repo`、前端 `KlineDayDetailPage` |
| US-3.4 任务结果 | `health_service`、`task_log_repo` |
| US-4.1 表列表 | `api/browse`、`browse_service`、`DataTable` |
| US-4.2 表浏览 | `browse_service`、多个 repo、前端 `DataTable` |
| US-4.3 浏览历史 | `browse_history_service`、`browse_history_repo`、前端 `HistoryPage` |
| US-5.1 详情入口 | 前端 `DataTable` → `StockDetailPage` |
| US-5.2 详情内容 | `stock_service`、`stock_repo` + `industry_repo` + `csrc_industry_repo` + `kline_repo` |
| US-6.1 下载指引 | 前端 `IndustryPage` 静态展示 + 版本查询 |
| US-6.2 上传解析 | `industry_service` → `sw_parser/*` |
| US-6.3 校验预览 | `sw_parser/validator`、`sw_parser/preview_builder` |
| US-6.4 版本记录 | `industry_service`、`industry_version_repo` |
| US-6.5 按天回滚 | `industry_service`、`industry_version_repo` |
| US-6.6 失效标记 | `industry_service` → `factor_result_repo.mark_stale` |
| US-7.1 参数面板 | `api/factor`、`factor_service`（校验）、前端 `ParamPanel` |
| US-7.2 一次算全层级 | `factor_service` → `factors/runner`（→ filters/returns/top_selection/aggregation/scoring），产出跨层级 `factor_result_row` |
| US-7.3 结果展示 | `factor_service.get_result(level=?)`、前端 `FactorPage` `DataTable` |
| US-7.4 板块下钻 | `factor_service.get_children_sectors`、`factor_result_repo`、前端 `FactorDrilldownPanel` |
| US-7.5 板块股票列表 | `factor_service.get_sector_stocks`（联查 `factor_result_row` + `sw_index_member_all` + 已算个股收益）、前端 `SectorStocksPanel` |
| US-7.6 面包屑 | 前端 `FactorBreadcrumb` + `factorBreadcrumbStore`（无后端） |
| US-7.7 配置管理 | `factor_config_repo`、前端 `FactorConfigPage` |
| US-7.8 失效提示 | `factor_service`、`factor_result_repo` |
| US-8.1 异常日志 | `api/admin`、`admin_service`、`error_log_repo` |
| US-9.1 添加用户 | `api/admin`、`admin_service`、`user_repo` |

---

## 8. 拆分预留（500 行硬约束下的预防性设计）

以下模块在设计时就必须以子文件形式落地，避免后期重构：

| 模块 | 预留拆分 |
| --- | --- |
| `sw_parser/` | 6 个子文件（见 §3.5） |
| `factors/` | 6 个子文件（见 §3.6） |
| `industry_service.py` | 若超过 400 行按流程拆：`industry_query.py` / `industry_upload.py` / `industry_rollback.py` |
| `health_service.py` | 若超过 400 行按视图拆：`health_summary.py` / `health_calendar.py` / `health_day_detail.py` |
| `api/industry.py` | 若超过 400 行按操作拆：`industry_query.py` / `industry_upload.py` / `industry_rollback.py`（路由前缀共用） |

其余模块单文件保持在 <400 行为警戒线；触发时再按子领域拆分。

---

## 9. 目录布局总览

```
backend/
├── app/
│   ├── api/                # HTTP 层
│   ├── services/           # 编排层
│   ├── repositories/       # 数据层
│   ├── adapters/
│   │   ├── baostock_adapter.py
│   │   ├── akshare_adapter.py
│   │   └── sw_parser/      # 申万解析器子模块
│   ├── factors/            # 因子子模块
│   ├── core/               # 基础设施（config/db/deps/envelope/errors/logging）
│   └── main.py             # FastAPI app 组装
├── alembic/                # 迁移脚本（DB 选型确定后启用）
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/           # 申万样例文件、K 线 fixture 等
└── pyproject.toml

frontend/
└── src/
    ├── api/
    ├── pages/
    ├── components/
    ├── store/
    ├── utils/
    └── main.tsx
```

---

## 10. 遗留决策（转交给 04 或 05）

| 项 | 转交去向 |
| --- | --- |
| 数据库选型（DuckDB / PostgreSQL / 其他） | 04_TECH_STACK.md ADR |
| K 线事实与复权派生数据如何分离 | 05_DATA_MODEL.md ADR-K01 |
| Alembic vs DuckDB 原生 SQL 迁移 | 04_TECH_STACK.md（依赖 DB 选型） |
| 因子结果失效标记的具体触发点 | 05_DATA_MODEL.md（`factor_result.stale` 字段 + 触发路径 audit） |
| 前端登录桩：`X-User` header vs Cookie | 04_TECH_STACK.md |
| 分页 / 排序 / 筛选参数 wire format | 04_TECH_STACK.md（envelope 章节） |
