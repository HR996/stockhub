# istock v1 技术方案选型

> 本文档记录每个技术组件的**选型 + 理由 + 替代方案 + 版本约束**，并对关键决策以 ADR 形式落地。
> 依赖的模块设计见 `docs/03_MODULES.md`。
> 本文档一经批准即为技术合同，后续 vibe-coding 任务不得跳过本文档另作选择。

---

## 1. 语言与运行时

| 项 | 选型 | 版本约束 | 理由 |
| --- | --- | --- | --- |
| 后端语言 | Python | **3.11+** | baostock、pandas 生态原生；类型注解 + `match` 语法完备 |
| 前端语言 | TypeScript | **5.3+** | 与 React 18 / Vite 5 契合；strict mode 全开 |
| 前端运行时 | Node.js | **20 LTS** | Vite 5 官方推荐；避免 22+ 生态兼容问题 |

**替代方案**：Python 3.10（放弃：`match` 语法与 typing 特性弱于 3.11）；Node 22（放弃：LTS 未收敛）。

---

## 2. 后端框架栈

| 项 | 选型 | 版本约束 | 理由 |
| --- | --- | --- | --- |
| Web 框架 | **FastAPI** | 0.110+ | 原生异步 / Pydantic v2 集成 / OpenAPI 自动生成；轻量适合单机 |
| 数据校验 | Pydantic v2 | 2.5+ | FastAPI 一等公民；性能优于 v1 |
| ORM | **SQLAlchemy** | 2.x | 2.0 typing / 声明式 mapping 成熟；同时支持 PostgreSQL 与 DuckDB |
| 迁移工具 | Alembic | 1.13+ | SQLAlchemy 官方迁移；支持 batch mode |
| 定时任务 | **APScheduler** | 3.10+ | 单机场景足够；比 Celery 轻量得多 |
| 测试 | pytest + pytest-asyncio | 8.x + 0.23+ | 生态标准 |
| Fixture 工厂 | factory-boy + Faker | 最新 | 减少测试样板代码 |
| Lint / Format | **Ruff** | 0.4+ | 一体化替代 black + flake8 + isort |
| 类型检查 | mypy | 1.8+ | strict mode 开启 |
| **包管理** | **uv** | 最新 | Rust 实现，比 pip / poetry 快 10× 以上；lockfile 支持 (`uv.lock`)；管理虚拟环境 + 依赖 + 工具执行一体化；CI 复现性强 |

**替代方案**：
- Django（放弃：过重，v1 不需要 admin / auth 生态）
- Flask（放弃：异步支持弱，OpenAPI 需手动搭建）
- Peewee（放弃：迁移生态弱）
- Celery + Redis（放弃：单机场景引入 broker 过度）
- pip + venv（放弃：无 lockfile，安装慢）
- poetry（放弃：解析速度慢；uv 是 Astral 官方新一代方案，与 Ruff 同生态）
- pdm / rye（放弃：uv 已收敛为社区首选）

---

## 3. 数据库选型（关键 ADR）

### 3.1 需求约束

用户已明确**排除 SQLite**。候选对比：DuckDB vs PostgreSQL vs MySQL。

**istock 的数据画像**：
- **写入路径**：定时任务批量入库 K 线（每日约 5000 支 × 3 复权口径 ≈ 15k 行 / 日）+ 偶发申万上传
- **读取路径以聚合分析为主**：因子计算需扫全市场股票收益、按行业分组聚合；数据浏览为分页查询
- 单机、少量并发用户、无 OLTP 高频写入场景
- 3 年 K 线累计约 5000 × 250 × 3 ≈ **375 万行**（不算冗余字段）

### 3.2 三方对比

| 维度 | DuckDB | PostgreSQL | MySQL |
| --- | --- | --- | --- |
| **部署方式** | 嵌入式（进程内 / 单文件），零额外服务 | 需部署服务进程 | 需部署服务进程 |
| **OLAP 聚合性能** | ★★★ 列式存储 + 向量化，因子聚合快 | ★★ 行存 + JIT，可用但需索引调优 | ★ 纯行存，大规模 group by 弱 |
| **OLTP 写入** | ★ 单写者约束（v0.10+ 支持并发） | ★★★ 成熟 MVCC | ★★★ 成熟 MVCC |
| **SQLAlchemy 支持** | 有官方 dialect（`duckdb-engine`），生态较新 | 一等公民，最成熟 | 一等公民，成熟 |
| **Alembic 支持** | 需自定义 batch mode（若涉及 ALTER 限制） | 完整支持 | 完整支持 |
| **JSON 字段** | 原生支持 | 一等公民（jsonb） | 5.7+ 支持但性能弱 |
| **窗口函数 / CTE** | 完整（PG 兼容语法） | 完整 | 8.0+ 完整 |
| **事务隔离** | 支持但简化 | 完整 | 完整 |
| **部署复杂度** | 无需独立服务 | 需安装并管理服务 | 需安装并管理服务 |
| **备份策略** | 复制 `.duckdb` 文件 | pg_dump | mysqldump |
| **运维复杂度** | 极低（无独立进程） | 中（连接池 / VACUUM / 参数调优） | 中（同 PG） |
| **社区成熟度** | 新兴，v1.x 稳定 | 极成熟 | 极成熟 |

### 3.3 决策：**PostgreSQL 15+**

**选择 PostgreSQL** 的核心理由：

1. **istock 是"数据基座 + 分析工具"，不是纯分析工具**。数据健康、任务日志、审计日志、申万版本管理都是典型 OLTP 需求，MVCC 与并发写事务是硬要求
2. **申万分类回滚**依赖版本快照的多表事务写入，PG 的事务成熟度是 DuckDB 追不上的
3. **375 万行日 K 线**在 PG 上通过复合索引 `(trade_date, ts_code)` 与分区（可选）完全可支撑；因子聚合走物化视图或临时表加速，性能满足单机分析需求
4. **生态最丰富**：SQLAlchemy / Alembic / psycopg[binary] 3.x / asyncpg 全部一等公民，社区问答密度最高
5. **jsonb** 覆盖因子配置、参数快照等半结构化存储场景（v1 无需 NoSQL）
6. **DuckDB 的 OLAP 性能优势在本项目规模下不显著**（单板块因子计算数据量 <100MB）；而 DuckDB 的单写者约束会在多任务定时同步 + 用户上传并发时产生锁竞争

**放弃 DuckDB 的具体理由**：
- 事务并发场景下的成熟度与文档密度落后 PG 至少 3 年
- 与 SQLAlchemy 2.x + Alembic 的组合在 ALTER TABLE / 索引管理上仍有边缘 bug
- 若未来 v2 引入历史市值 / 分钟 K，OLAP 优势才显著；v1 尚未到那个规模

**放弃 MySQL 的具体理由**：
- 分析型 group by / 窗口函数性能弱于 PG
- jsonb / 数组类型不如 PG 灵活
- Python 生态在 PG 侧更繁荣

### 3.4 版本与部署

| 项 | 值 |
| --- | --- |
| PostgreSQL 版本 | **15.x**（16 亦可，锁定 15+） |
| Python 驱动 | `psycopg[binary]` 3.1+（不用旧 psycopg2） |
| 部署形态 | PostgreSQL 系统服务，或独立数据库服务器 |
| 备份 | 每日凌晨 `pg_dump` 到 `/backup/`，保留 30 天 |
| 连接池 | SQLAlchemy 内建 `QueuePool`，v1 单机不引入 pgbouncer |
| 迁移 | Alembic（因用 PG，不需 batch mode） |

### 3.5 后续可能演进

- 若 v2 引入历史市值 / 分钟 K 使数据量 >1 亿行，可**将 K 线相关聚合迁至 DuckDB**（PG 主 + DuckDB 分析双库），本次不做
- 若并发用户显著增长，再引入 pgbouncer

---

## 4. 数据源

### 4.1 主源：baostock

| 项 | 值 |
| --- | --- |
| 库版本 | `baostock` 最新稳定 pip 版本 |
| 认证 | 匿名 `bs.login()` |
| 覆盖 | 股票基础信息 / 交易日历 / 日 K 线 / `tradestatus` / `isST` / 停牌与 ST 判定 |
| 关键 API | `query_all_stock` / `query_stock_basic` / `query_history_k_data_plus` / `query_trade_dates` |
| adjustflag 语义 | **`1=后复权 / 2=前复权 / 3=不复权`** —— 全项目锁定：因子算法用 `2` |
| 生命周期 | 每次任务用 context manager 包裹 login/logout；异常时确保 logout |
| 错误处理 | 捕获 `error_code != '0'` 转为 `AdapterDataError`；网络异常转为 `AdapterConnectionError` |

**已知坑**（写入 `sw_parser` 与 `baostock_adapter` 的 cheatsheet）：
- `date` 字段是字符串，需显式转 `date`
- 停牌日仍会返回 K 线行但价格字段为空字符串，需过滤
- `outDate` 未退市股票为空字符串，不是 null

### 4.2 最新市值：baostock 单源合成（P1-04 决策变更）

**背景**：曾计划用 akshare `stock_zh_a_spot_em` 兜底最新市值，但实测东财 push 端点在部分环境下持续拒绝匿名请求（`RemoteDisconnected`），akshare 内置重试无法穿透。**改为完全使用 baostock，通过总股本 × 收盘价合成最新市值**。

| 项 | 值 |
| --- | --- |
| 数据源 | baostock `query_profit_data`（季度财报接口，含 `totalShare` / `liqaShare`）+ `k_line_daily.close_raw`（快照日收盘价） |
| 单位 | `totalShare` / `liqaShare` 的单位是**股**（不是万股）；乘以收盘价（元/股）得到市值（元） |
| 拉取节奏 | **totalShare 按新季披露拉**（`_quarter_of()` 用上一季度以避开新季未披露窗口）；日常市值刷新只重算 `close × 已存 total_share` |
| 合成路径 | `market_cap_service.synthesize_for()`：`fetch_profit_data(bs_code, year, quarter)` → 拿 `totalShare` → 联查 `kline_repo.get(ts_code, snapshot_date).close_raw` → 相乘并四舍五入到 2 位 → 落 `latest_market_cap` |
| 缺失路径 | profit_data 或 K 线任一缺失 → `market_cap_source='baostock_missing'` + `total_market_cap=null`；服务不因单支缺失中断整批 |
| 已知覆盖率 | 沪深主板 / 创业板 / 科创板普通股完全覆盖；**部分北交所股票 profit_data 无数据**（如 `bj.430047`），标为 missing |
| Adapter 异常 | 不阻塞：service 层 `try/except` 捕获 `AdapterConnectionError` / `AdapterDataError` → 记 warning 日志 → 该股按 missing 处理 |

**边界**：
- **不再依赖 akshare**（已从 pyproject 移除）
- 不做历史当日市值（v1 只保留最新一版）
- Service 假设调用者已经在 `baostock_session` 上下文内、且 K 线已入库（K 线同步应先于市值合成执行）

### 4.3 申万分类：手工上传

由用户从申万官网下载压缩包上传，服务端解析。技术栈见 §6。

---

## 5. 前端框架栈

| 项 | 选型 | 版本约束 | 理由 |
| --- | --- | --- | --- |
| UI 框架 | **React** | 18.2+ | Ant Design 5 一等公民；生态最成熟 |
| 构建 | **Vite** | 5.x | 冷启动 / HMR 最快；配置最少 |
| UI 组件库 | **Ant Design** | 5.x | 表格 / 表单 / 弹窗 / 上传组件覆盖度最高，与 istock 需求高度吻合 |
| 状态管理 | **Zustand** | 4.x | 轻量、TS 友好；比 Redux Toolkit 简单 5 倍 |
| 数据请求 | **@tanstack/react-query** | 5.x | 缓存 / 失效 / 重试机制契合"数据健康 + 版本失效"场景 |
| HTTP | axios | 1.6+ | 拦截器体系成熟；便于统一 envelope 与 X-User header |
| K 线图 | **lightweight-charts** | 4.x | TradingView 官方，K 线体验最佳 |
| 通用图表 | ECharts | 5.x | 月历热力图 / 柱状 / 饼图 |
| 表格拖拽 | @dnd-kit | 6.x | AntD Table 字段列拖拽 |
| 路由 | react-router | 6.x | 生态标准 |
| 表单 | AntD Form + zod | AntD 内置 + zod 3.x | zod 做前端参数校验（因子参数） |

**替代方案**：
- Vue 3（放弃：用户已确认 React）
- Redux Toolkit（放弃：v1 状态复杂度不需要）
- SWR（放弃：`react-query` 的失效机制更契合 istock 的"版本失效标记"需求）
- Highcharts（放弃：付费限制）
- Recharts（放弃：K 线弱于 lightweight-charts）

---

## 6. 压缩包与 Excel 解析栈

**核心 —— 服务端必须支持 rar 解压 + xls / xlsx 解析**（US-6.2）：

| 项 | 选型 | 版本约束 | 依赖 |
| --- | --- | --- | --- |
| RAR 解压 | **`rarfile`** | 4.2+ | **需系统安装 `unrar` 二进制**（apt: `unrar` 或 `unar`） |
| ZIP 解压 | Python stdlib `zipfile` | Python 3.11+ 内置 | 无 |
| xlsx 读取 | **`openpyxl`** | 3.1+ | 无 |
| xls 读取 | **`xlrd==1.2.0`**（**版本锁死**） | 1.2.0 | xlrd 2.0+ 已移除 xls 支持，必须钉在 1.2.0 |
| 统一入口 | pandas | 2.2+ | pandas 会自动路由到 openpyxl / xlrd |

**部署要求**：在操作系统中安装 `unrar-free`、`unrar` 或 `unar`。

**替代方案**：
- `patool` / `pyunpack`（放弃：抽象层过深、错误信息含糊）
- `unrar-cffi`（放弃：编译复杂）
- 强制转 zip（放弃：需求已明确支持 rar）

**决策记录**：
- xls 与 xlsx 分别走不同库，pandas 只作外层路由；`sw_parser/excel_parser.py` 内部封装此细节
- 若压缩包内含未知格式文件，`archive_reader.py` 先列清单让 `excel_parser.py` 只处理 `.xls` / `.xlsx`，其余静默忽略并记入解析日志

---

## 7. API 契约

### 7.1 统一响应 envelope

所有 API 返回：
```json
{
  "success": true,
  "data": { ... },
  "message": ""
}
```

- `success`：布尔，标识业务是否成功（HTTP 状态码只标识传输层）
- `data`：任意 JSON；空对象 `{}` 或空数组 `[]`，不返回 `null` 除非语义确实是"无"
- `message`：失败时的可读文案；成功时空串

### 7.2 错误码约定

在 `data` 中携带 `code` 字段：

| code 前缀 | 含义 |
| --- | --- |
| `AUTH_*` | 认证 / 密码 / 权限 |
| `VALIDATION_*` | 参数校验 |
| `NOT_FOUND_*` | 资源不存在 |
| `CONFLICT_*` | 冲突（重复用户名等） |
| `ADAPTER_*` | 外部数据源错误 |
| `PARSER_*` | 申万解析错误 |
| `INTERNAL_*` | 未分类内部错误 |

### 7.3 分页

请求：`?page=1&page_size=50`
响应 `data` 结构：
```json
{
  "items": [...],
  "total": 12345,
  "page": 1,
  "page_size": 50
}
```

### 7.4 排序 / 筛选

- 排序：`?order_by=trade_date&order=desc`（多字段用逗号分隔）
- 筛选：POST body 中的 `filters` 字段（对象数组），格式：
  ```json
  { "field": "ts_code", "op": "in", "value": ["600000", "000001"] }
  ```
- op 支持：`eq`、`ne`、`in`、`nin`、`gt`、`ge`、`lt`、`le`、`like`

### 7.5 时间格式

全站 ISO 8601（`YYYY-MM-DDTHH:MM:SS+08:00`），交易日单纯用 `YYYY-MM-DD`。

---

## 8. 认证与审计

### 8.1 登录桩（v1 简化方案）

- 前端登录时将用户名保存在 localStorage
- axios 拦截器每次请求自动附加 `X-User: <username>` header
- 后端 `deps.get_current_user` 从 header 读取并校验是否在预配置用户列表
- **v1 不做 JWT / Session Cookie**（少量用户、内网环境）

### 8.2 敏感操作密码

- 敏感操作 API 要求请求头额外携带 `X-Admin-Password: <sha256>`（客户端预 hash）
- 后端配置项 `ADMIN_PASSWORD_HASH` 存 hash，不存明文
- 校验失败写入审计日志（用户名 + 操作 + IP + 时间）

### 8.3 审计日志

- 所有写操作强制记 `X-User`
- 敏感操作记 `X-User + X-Admin-Password 校验结果`
- 写入 `audit_log` 表，异步写不阻塞主流程

**替代方案**：
- JWT（放弃：v1 无需 stateless；引入即需要密钥管理）
- Session Cookie + Redis（放弃：v1 不引入 Redis）

---

## 9. 目录布局

```
istock/
├── backend/
│   ├── app/
│   │   ├── api/                  # 每个领域一个路由文件
│   │   ├── services/             # 编排层
│   │   ├── repositories/         # 数据访问层
│   │   ├── adapters/
│   │   │   ├── baostock_adapter.py     # 主 adapter（stock_basic / trade_cal / K 线）
│   │   │   ├── baostock_profit.py      # profit_data 独立子模块（供市值合成）
│   │   │   ├── baostock_types.py       # DTO 集中处
│   │   │   └── sw_parser/              # 6 个子文件
│   │   ├── factors/                    # 6 个子文件
│   │   ├── core/                 # config / db / deps / envelope / errors / logging
│   │   └── main.py
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/             # 申万样例文件、K 线 fixture
│   ├── pyproject.toml
│   ├── uv.lock                   # uv 生成的锁文件（提交入库）
├── frontend/
│   ├── src/
│   │   ├── api/                  # 与后端 api/ 一一对应
│   │   ├── pages/
│   │   ├── components/
│   │   ├── store/
│   │   ├── utils/
│   │   ├── router.tsx
│   │   └── main.tsx
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
├── docs/
├── prompt/
├── sw-data/                      # 申万样例数据（开发期用）
└── PROJECT.md
```

---

## 10. 部署与本地开发

| 项 | 值 |
| --- | --- |
| 后端包管理 | **uv**（`uv sync` 装依赖、`uv run` 跑命令、`uv add / remove` 增删依赖） |
| 后端锁文件 | `uv.lock`（提交入库，保证跨环境复现） |
| 本地开发 | PostgreSQL 系统服务 + 后端 uvicorn + 前端 Vite dev server |
| 后端启动（宿主） | `uv run uvicorn app.main:app --reload --port 8000` |
| 后端测试（宿主） | `uv run pytest` |
| 后端 lint（宿主） | `uv run ruff check app/ tests/` / `uv run mypy app/` |
| 前端启动 | `npm run dev`（Vite 默认 5173） |
| 生产部署 | nginx 托管前端静态资源并反代后端 API；后端由 systemd / supervisor 管理 |
| 环境变量 | `.env`（gitignore）+ `.env.example`（模板） |
| 关键环境变量 | `DATABASE_URL` / `ADMIN_PASSWORD_HASH` / `PRECONFIGURED_USERS` / `BAOSTOCK_ENABLED` / `AKSHARE_ENABLED` |

---

## 11. 关键决策汇总（ADR 索引）

| ID | 决策 | 章节 |
| --- | --- | --- |
| **ADR-01** | 后端语言 Python 3.11+ | §1 |
| **ADR-02** | 数据库使用 PostgreSQL 15+，排除 SQLite / DuckDB / MySQL | §3.3 |
| **ADR-03** | ORM = SQLAlchemy 2.x + Alembic | §2 |
| **ADR-04** | 定时任务使用 APScheduler，不引入 Celery / Redis | §2 |
| **ADR-05** | baostock adjustflag 语义锁定 `1=后复权 / 2=前复权 / 3=不复权`，因子用 `2` | §4.1 |
| **ADR-06** | 最新市值 = **baostock 单源合成**（`totalShare × close_raw`），不再使用 akshare | §4.2 |
| **ADR-07** | 前端 React 18 + Vite 5 + AntD 5 + Zustand + react-query | §5 |
| **ADR-08** | K 线图使用 lightweight-charts，通用图表使用 ECharts | §5 |
| **ADR-09** | RAR 解压使用 `rarfile` + 系统 `unrar` 二进制 | §6 |
| **ADR-10** | xls 使用 `xlrd==1.2.0`（版本锁死），xlsx 使用 `openpyxl` | §6 |
| **ADR-11** | 登录桩 = `X-User` header + localStorage，不引入 JWT | §8.1 |
| **ADR-12** | 敏感操作使用 `X-Admin-Password`（客户端 sha256 预 hash） | §8.2 |
| **ADR-13** | API envelope 统一 `{success, data, message}` | §7.1 |
| **ADR-14** | Lint 使用 Ruff（一体化替代 black + flake8 + isort） | §2 |
| **ADR-15** | 后端包管理使用 uv（排除 pip / poetry / pdm / rye），锁文件 `uv.lock` 提交入库 | §2、§10 |
| **ADR-16** | 最新市值 = baostock `query_profit_data.totalShare × k_line_daily.close_raw`；缺任一侧 → `market_cap_source='baostock_missing'`；不追溯历史当日市值。**旧方案（akshare 兜底）在实测中因东财风控不可用被弃用** | §4.2、P1-04 |

---

## 12. 转交给 05_DATA_MODEL 的项

- K 线 raw 事实表、复权因子和最新 QFQ 缓存的职责边界
- `latest_market_cap` 表结构（含 `market_cap_source` 字段）
- `sw_index_classify` / `sw_index_member_all` 与 `sw_industry_version` 的外键关系
- `factor_result` 的 `stale` / `stale_reason` 字段设计
- `audit_log` 与 `error_log` 的字段清单
- `browse_history` 的 `page_state` 字段（jsonb）

---

## 13. 后续演进（非本文档决策，仅登记）

- v2 引入历史市值 / 分钟 K 线时评估是否上 DuckDB 分析副本
- 用户增长 >20 时引入 pgbouncer 连接池
- 前端类型定义可评估 openapi codegen（v1 保持手工对齐）
- CI/CD 引入 GitHub Actions（v1 优先本地开发）
