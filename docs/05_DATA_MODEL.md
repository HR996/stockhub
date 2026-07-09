# istock v1 数据库设计

> ⚠️ **申万分类相关设计已更新**（2026-07-08）：`sw_industry_version` / `sw_index_classify` / `sw_index_member_all` 三表所描述的"版本化 + is_current 切换 + 上传压缩包"方案已废弃。当前实现改走 Tushare Pro API，只保留 `sw_industry_classify` + `sw_industry_member` 两张快照表（无版本、每次同步 TRUNCATE + INSERT）。详见 `prompt/reference/tushare_sw_cheatsheet.md` 与 `backend/alembic/versions/0004_sw_industry_tables.py`。以下文本仅保留作为历史设计存档。

> 本文档给出 v1 全部表的清单、字段中文说明、DDL 草案、关键索引与外键。
> DB 选型见 `docs/04_TECH_STACK.md §3` —— **PostgreSQL 15+**。
> 模块划分见 `docs/03_MODULES.md`；用户故事见 `docs/02_USER_STORIES.md`。
> 本文档一经批准即为数据合同，后续 vibe-coding 任务以 Alembic 迁移为唯一变更手段。

---

## 1. 表清单总览

| 表名 | 用途 | 关联用户故事 |
| --- | --- | --- |
| `user_account` | 预配置用户名与添加用户 | US-1.1、US-9.1 |
| `audit_log` | 关键操作审计日志 | US-1.3、US-1.4 |
| `error_log` | 系统异常日志 | US-8.1 |
| `stock_basic` | 股票基础信息 | US-2.1、US-5.2 |
| `trade_calendar` | 交易日历 | US-2.1、US-7.1 |
| `k_line_daily` | 未复权日 K 线事实表 | US-2.1 ~ US-2.3 |
| `k_line_qfq_latest` | 最新基准日前复权展示缓存 | US-5.1 |
| `stock_adj_factor` | 复权因子（Tushare） | US-2.2、US-2.3 |
| `latest_market_cap` | 最新市值（Tushare daily_basic） | US-2.4 |
| `csrc_industry` | 证监会行业分类 | US-3.1、US-5.2 |
| `sw_industry_version` | 申万分类版本快照 | US-6.4、US-6.5 |
| `sw_index_classify` | 申万分类树（对齐 TuShare `index_classify`） | US-6.2 ~ US-6.5 |
| `sw_index_member_all` | 申万成分构成（对齐 TuShare `index_member_all`） | US-6.2 ~ US-6.5 |
| `data_update_task` | 数据更新任务日志 | US-2.1、US-3.4 |
| `factor_config` | 因子参数配置（用户命名保存） | US-7.7 |
| `factor_result` | 因子计算结果（跨层级；含失效标记） | US-7.2、US-7.8 |
| `factor_result_row` | 因子计算结果的板块级明细（含 `level` / `parent_sector_code`） | US-7.2、US-7.4 |
| `factor_result_stock` | 因子计算下的个股收益快照（供板块股票列表） | US-7.5 |
| `browse_history` | 浏览历史与页面状态 | US-4.3 |

共 18 张表，以下按领域分组说明。

---

## 2. 全局字段约定

- 主键统一为 `id BIGSERIAL PRIMARY KEY`（业务键作为 UNIQUE 索引，不当主键）
- 时间字段统一 `TIMESTAMPTZ`（时区带偏移）
- 交易日单纯用 `DATE`
- 审计四件套：`created_at` / `created_by` / `updated_at` / `updated_by`（`_by` 存 `X-User` 值）
- 软删除不用（v1 明确删除即物理删除；申万分类通过版本快照实现"逻辑保留"）
- 半结构化字段用 `JSONB`（因子参数、页面状态、异常上下文）

---

## 3. 用户与审计

### 3.1 `user_account` — 预配置用户名

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `username` | VARCHAR(64) | N | 用户名（业务唯一） |
| `is_active` | BOOLEAN | N | 是否可登录，默认 true |
| `created_at` | TIMESTAMPTZ | N | 创建时间 |
| `created_by` | VARCHAR(64) | Y | 创建者（首批种子用户为 null） |

**索引**：`UNIQUE(username)`
**说明**：v1 无角色 / 权限；仅通过是否在此表中判定登录合法性。

### 3.2 `audit_log` — 关键操作审计

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `username` | VARCHAR(64) | N | 操作用户名（`X-User` 落库） |
| `action` | VARCHAR(64) | N | 操作类型（如 `INDUSTRY_UPLOAD` / `INDUSTRY_ROLLBACK` / `USER_ADD`） |
| `target_type` | VARCHAR(64) | Y | 操作对象类型（如 `industry_version` / `user_account`） |
| `target_id` | VARCHAR(128) | Y | 操作对象业务 ID |
| `admin_password_ok` | BOOLEAN | Y | 敏感操作时的密码校验结果 |
| `success` | BOOLEAN | N | 操作最终结果 |
| `error_message` | TEXT | Y | 失败原因 |
| `context` | JSONB | Y | 操作上下文（参数、影响面等） |
| `client_ip` | VARCHAR(64) | Y | 请求来源 IP |
| `created_at` | TIMESTAMPTZ | N | 记录时间 |

**索引**：`(username, created_at DESC)`；`(action, created_at DESC)`

### 3.3 `error_log` — 系统异常

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `severity` | VARCHAR(16) | N | 严重程度（`INFO` / `WARN` / `ERROR` / `FATAL`） |
| `task_type` | VARCHAR(64) | Y | 关联任务类型（`SYNC_KLINE` / `INDUSTRY_PARSE` 等） |
| `summary` | VARCHAR(255) | N | 异常摘要 |
| `detail` | TEXT | Y | 异常详情（含 traceback） |
| `impact_scope` | JSONB | Y | 影响范围（含哪些日期 / 股票 / 表） |
| `status` | VARCHAR(32) | N | 处理状态（`OPEN` / `ACK` / `RESOLVED`） |
| `occurred_at` | TIMESTAMPTZ | N | 发生时间 |
| `resolved_at` | TIMESTAMPTZ | Y | 处理完成时间 |
| `created_at` | TIMESTAMPTZ | N | 记录时间 |

**索引**：`(occurred_at DESC)`；`(severity, status)`；`(task_type, occurred_at DESC)`

---

## 4. 数据基座

### 4.1 `stock_basic` — 股票基础信息

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `ts_code` | VARCHAR(16) | N | 股票代码（业务唯一，格式对齐 TuShare `600000.SH`） |
| `bs_code` | VARCHAR(16) | N | baostock 兼容代码（`sh.600000`，由 `ts_code` 派生） |
| `name` | VARCHAR(64) | N | 股票名称 |
| `market` | VARCHAR(16) | N | 市场（`SH` / `SZ` / `BJ`） |
| `list_date` | DATE | Y | 上市日期 |
| `delist_date` | DATE | Y | 退市日期，null = 未退市 |
| `is_bj` | BOOLEAN | N | 是否北交所 |
| `is_common` | BOOLEAN | N | 是否普通股票（剔除基金 / ETF / 指数等） |
| `is_st` | BOOLEAN | N | 最新是否 ST（v1 用最新名称判定，不建历史 ST 表） |
| `updated_at` | TIMESTAMPTZ | N | 最后同步时间 |
| `updated_by` | VARCHAR(64) | Y | 最后同步任务标识（如 `scheduler` / `manual`） |

**索引**：`UNIQUE(ts_code)`；`UNIQUE(bs_code)`；`(market)`；`(is_common, is_bj)`

### 4.2 `trade_calendar` — 交易日历

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `cal_date` | DATE | N | 日期（业务唯一） |
| `is_open` | BOOLEAN | N | 是否交易日 |
| `updated_at` | TIMESTAMPTZ | N | 最后同步时间 |

**索引**：`UNIQUE(cal_date)`；`(is_open, cal_date)`
**用法**：因子 `start_date = basedate 向前 window 个交易日`，SQL 层 `WHERE is_open AND cal_date <= basedate ORDER BY cal_date DESC LIMIT window`。

### 4.3 `k_line_daily` — 日 K 线

**ADR-K01：事实表只保存未复权行情。** 复权因子独立保存，研究计算动态复权，展示使用可重建缓存。

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `ts_code` | VARCHAR(16) | N | 股票代码 |
| `trade_date` | DATE | N | 交易日 |
| `open_raw` / `high_raw` / `low_raw` / `close_raw` / `preclose_raw` | NUMERIC(12,4) | Y | 不复权价（Tushare `daily`） |
| `volume` | NUMERIC(20,2) | Y | 成交量（股；Tushare `vol` 手 × 100） |
| `amount` | NUMERIC(20,4) | Y | 成交额（元；Tushare `amount` 千元 × 1000） |
| `turn` | NUMERIC(10,4) | Y | 换手率 |
| `pct_chg` | NUMERIC(10,4) | Y | 涨跌幅 |
| `trade_status` | SMALLINT | N | 交易状态（`1=交易 / 0=停牌`；Tushare 停牌日缺行，由 data service 补占位行） |
| `is_st_row` | BOOLEAN | N | 该行 ST 状态（v1 由当前 `stock_basic.is_st` 派生） |
| `updated_at` | TIMESTAMPTZ | N | 最后同步时间 |

**索引**：
- `UNIQUE(ts_code, trade_date)` — 幂等 upsert 键
- `(trade_date, ts_code)` — 单日健康详情、月历状态、因子按日跨股票查询
- `(ts_code, trade_date DESC)` — 股票详情倒序 K 线

**分区**（可选，v1 不必开）：按 `trade_date` 年度分区可将扫描范围缩至相关年份；v1 数据量下暂不启用，等表 >5000 万行再评估。

**null 语义**：
- 停牌日：Tushare `daily` 不返回该日行情；全市场日线成功拉取后，data service 对活跃但缺失的股票补 `trade_status=0` 且价格全 null 的占位行
- 未上市或已退市日：不生成行

### 4.4 `stock_adj_factor` — 复权因子

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `ts_code` | VARCHAR(16) | N | 股票代码 |
| `trade_date` | DATE | N | 交易日 |
| `adj_factor` | NUMERIC(18,8) | N | Tushare 复权因子 |
| `source` | VARCHAR(32) | N | 数据来源，默认 `tushare` |
| `updated_at` | TIMESTAMPTZ | N | 最后同步时间 |

**索引**：
- `UNIQUE(ts_code, trade_date)` — 幂等 upsert 键
- `(trade_date, ts_code)` — 单日批量写入与核对
- `(ts_code, trade_date DESC)` — 取股票最新复权因子

**复权计算**：
- 任意基准日前复权：`qfq(t, B) = raw(t) * factor(t) / factor(B)`
- 因子收益直接使用 `raw_end * factor_end / (raw_start * factor_start)`。

### 4.5 `k_line_qfq_latest` — 最新前复权展示缓存

缓存保存 `ts_code`、`trade_date`、前复权 OHLC/preclose、`base_date`、`base_adj_factor` 和 `calculated_at`。唯一键为 `(ts_code, trade_date)`。该表不是权威数据，可以从 `k_line_daily + stock_adj_factor` 完整重建。

### 4.6 `latest_market_cap` — 最新市值

**数据源**：Tushare `daily_basic`。`total_mv/circ_mv` 按万元返回，入库转为元；`total_share/float_share` 按万股返回，入库转为股。

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `ts_code` | VARCHAR(16) | N | 股票代码（业务唯一） |
| `total_market_cap` | NUMERIC(20,2) | Y | 总市值（元，Tushare `total_mv` 万元 × 10000） |
| `circ_market_cap` | NUMERIC(20,2) | Y | 流通市值（元，Tushare `circ_mv` 万元 × 10000） |
| `total_share` | NUMERIC(20,2) | Y | 总股本（股，Tushare `total_share` 万股 × 10000） |
| `liqa_share` | NUMERIC(20,2) | Y | 流通股本（股，Tushare `float_share` 万股 × 10000） |
| `snapshot_close` | NUMERIC(12,4) | Y | 快照日收盘价（不复权，`k_line_daily.close_raw`） |
| `snapshot_date` | DATE | Y | 快照日（用于对齐 close_raw） |
| `market_cap_source` | VARCHAR(32) | N | 数据来源枚举：`tushare_daily_basic` / `tushare_missing` |
| `snapshot_at` | TIMESTAMPTZ | N | 抓取快照时间戳（合成执行时间） |
| `updated_at` | TIMESTAMPTZ | N | 落库更新时间 |

**索引**：`UNIQUE(ts_code)`

**用法**：
- 因子过滤条件 `total_market_cap >= 100 亿元` 直接查此表；null 值视为不满足过滤条件
- 覆盖率注意：Tushare 权限或单日缺失时写 `market_cap_source='tushare_missing'`

### 4.7 `csrc_industry` — 证监会行业分类

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `ts_code` | VARCHAR(16) | N | 股票代码 |
| `industry_code` | VARCHAR(32) | N | 行业代码 |
| `industry_name` | VARCHAR(64) | N | 行业名称 |
| `updated_at` | TIMESTAMPTZ | N | 最后同步时间 |

**索引**：`UNIQUE(ts_code)`；`(industry_code)`
**说明**：证监会行业只保留最新版本，v1 不做历史版本；变化频率极低。

---

## 5. 申万行业分类（核心，含版本管理）

### 5.1 `sw_industry_version` — 版本快照头

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键（即 `version_id`） |
| `version_no` | VARCHAR(32) | N | 版本号（`YYYYMMDD-<seq>`，业务唯一） |
| `source_file_name` | VARCHAR(255) | N | 上传的原始文件名 |
| `source_file_hash` | VARCHAR(64) | N | 上传文件 sha256 |
| `impact_summary` | JSONB | N | 影响面摘要（新增行业数 / 删除行业数 / 变更股票映射数等） |
| `is_current` | BOOLEAN | N | 是否当前生效版本（同时只有一条为 true） |
| `created_at` | TIMESTAMPTZ | N | 创建时间 |
| `created_by` | VARCHAR(64) | N | 上传用户名 |

**索引**：`UNIQUE(version_no)`；`UNIQUE(is_current) WHERE is_current`（PG 部分唯一索引，保证同时只有一条 current）
**回滚流程**：将当前 `is_current=true` 的版本置 false，再将目标版本置 true，事务原子完成；后续查询默认走 `is_current=true` 的行。

### 5.2 `sw_index_classify` — 分类树（对齐 TuShare `index_classify`）

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `version_id` | BIGINT | N | 外键 → `sw_industry_version.id` |
| `index_code` | VARCHAR(32) | N | 行业指数代码（业务键之一） |
| `industry_name` | VARCHAR(128) | N | 行业名称 |
| `level` | VARCHAR(4) | N | 层级（`L1` / `L2` / `L3`） |
| `industry_code` | VARCHAR(32) | Y | 行业业务代码 |
| `is_pub` | BOOLEAN | Y | 是否发布 |
| `parent_code` | VARCHAR(32) | Y | 父级 `index_code`（L2 指向 L1，L3 指向 L2） |
| `src` | VARCHAR(16) | N | 来源（固定 `SW`） |
| `created_at` | TIMESTAMPTZ | N | 创建时间 |

**索引**：
- `UNIQUE(version_id, index_code)` — 版本内业务唯一
- `(version_id, level)`
- `(version_id, parent_code)`

### 5.3 `sw_index_member_all` — 成分构成（对齐 TuShare `index_member_all`）

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `version_id` | BIGINT | N | 外键 → `sw_industry_version.id` |
| `l1_code` | VARCHAR(32) | Y | 一级行业 index_code |
| `l1_name` | VARCHAR(128) | Y | 一级行业名称 |
| `l2_code` | VARCHAR(32) | Y | 二级行业 index_code |
| `l2_name` | VARCHAR(128) | Y | 二级行业名称 |
| `l3_code` | VARCHAR(32) | Y | 三级行业 index_code |
| `l3_name` | VARCHAR(128) | Y | 三级行业名称 |
| `ts_code` | VARCHAR(16) | N | 股票代码 |
| `name` | VARCHAR(64) | N | 股票名称（快照时的名称） |
| `in_date` | DATE | Y | 纳入日期 |
| `out_date` | DATE | Y | 剔除日期，null = 仍在成分中 |
| `is_new` | BOOLEAN | Y | 是否最新有效条目 |
| `created_at` | TIMESTAMPTZ | N | 创建时间 |

**索引**：
- `(version_id, ts_code)` — 因子聚合按股票查行业主键
- `(version_id, l1_code)` / `(version_id, l2_code)` / `(version_id, l3_code)` — 按不同层级查成分
- `(version_id, is_new)` — 只查当前生效成分

**用法**：因子按 `level=L2` 计算板块动量时，从 `sw_index_member_all WHERE version_id=<current> AND is_new=true` 取每支股票的 `l2_code` 作为分组键。

---

## 6. 数据更新任务

### 6.1 `data_update_task` — 任务日志

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `task_type` | VARCHAR(64) | N | 任务类型（如 `TUSHARE_INIT` / `TUSHARE_UPDATE_DAILY` / `TUSHARE_SYNC_BASIC` / `TUSHARE_SYNC_TRADE_CAL` / `TUSHARE_RECOMPUTE_ADJUSTED` / legacy `SYNC_*`） |
| `task_key` | VARCHAR(128) | Y | 幂等键（如 `SYNC_KLINE:2026-07-07`） |
| `status` | VARCHAR(16) | N | 状态（`RUNNING` / `SUCCESS` / `FAILED` / `PARTIAL`） |
| `started_at` | TIMESTAMPTZ | N | 开始时间 |
| `finished_at` | TIMESTAMPTZ | Y | 结束时间 |
| `expected_count` | INTEGER | Y | 应处理数（如应更新股票数） |
| `success_count` | INTEGER | Y | 成功数 |
| `missing_count` | INTEGER | Y | 缺失数 |
| `error_count` | INTEGER | Y | 异常数 |
| `error_summary` | JSONB | Y | 错误摘要（分类计数 + 少量样例） |
| `created_by` | VARCHAR(64) | N | 触发者（`scheduler` / 用户名） |

**索引**：
- `(task_type, started_at DESC)` —— 任务日志页倒序展示
- `UNIQUE(task_type, task_key) WHERE task_key IS NOT NULL` —— 幂等约束（部分唯一索引）
- `(status, started_at DESC)`

**用法**：
- 单日健康详情优先从 `TUSHARE_UPDATE_DAILY:<date>` 取，legacy 数据可兼容 `SYNC_KLINE:<date>`
- 月历绿/黄/红状态由 `expected_count` 与 `success_count` / `missing_count` 计算

---

## 7. 因子

### 7.1 `factor_config` — 用户命名保存的参数配置

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `name` | VARCHAR(128) | N | 用户命名（业务唯一） |
| `params` | JSONB | N | 参数快照（`basedate`/`window`/`top_ratio`/`classification`/`level`/`return_method`/`score_method`） |
| `owner` | VARCHAR(64) | N | 创建者（v1 全体共享，字段仅审计） |
| `created_at` | TIMESTAMPTZ | N | 创建时间 |
| `updated_at` | TIMESTAMPTZ | N | 最后修改时间 |
| `updated_by` | VARCHAR(64) | N | 最后修改者 |

**索引**：`UNIQUE(name, owner)`；`(owner, updated_at DESC)`

**参数字段说明**：`params.level` 表示"用户偏好的默认展示层级"，**不影响计算范围** —— 每次计算固定按 SW2021 跑全部层级（L1/L2/L3）。v1 首版只支持 `classification=SW`。

### 7.2 `factor_result` — 计算结果头（跨层级）

**语义变更（P1-04 后需求细化）**：一条 `factor_result` 代表**一次因子计算**，同时包含所选行业体系下**全部层级**的板块结果。层级信息落在 `factor_result_row.level` 上，不在头表。

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `params` | JSONB | N | 参数快照（含全部参数；`params.level` 是"默认展示层级"，非计算范围） |
| `basedate` | DATE | N | 基准日（冗余出来供索引） |
| `start_date` | DATE | N | 按交易日历回溯得到的起始交易日 |
| `classification` | VARCHAR(16) | N | 行业体系；v1 固定 `SW` |
| `industry_snapshot_at` | TIMESTAMPTZ | Y | 计算时依赖的 SW 快照时间（取 `sw_industry_classify/member.created_at` 最大值） |
| `stale` | BOOLEAN | N | 失效标记，默认 false |
| `stale_reason` | VARCHAR(64) | Y | 失效原因（`INDUSTRY_ROLLBACK` / `INDUSTRY_UPDATE` / `KLINE_UPDATED` 等） |
| `stale_at` | TIMESTAMPTZ | Y | 被标记失效的时间 |
| `created_at` | TIMESTAMPTZ | N | 计算时间 |
| `created_by` | VARCHAR(64) | N | 计算用户 |

**索引**：
- `(created_at DESC)`
- `(basedate, created_at DESC)` — 按基准日查历史结果
- `(stale)` — 前端筛选
- `(classification, basedate)` — 结果查询按行业体系过滤

### 7.3 `factor_result_row` — 每次计算的板块级明细（含层级 + 父级）

**语义变更（P1-04 后需求细化）**：新增 `level` 与 `parent_sector_code` 支持**跨层级存储**与**下钻查询**。

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `result_id` | BIGINT | N | 外键 → `factor_result.id`（ON DELETE CASCADE） |
| `level` | VARCHAR(4) | N | 板块层级（`L1` / `L2` / `L3`；CSRC 只用 `L1`） |
| `sector_code` | VARCHAR(32) | N | 板块代码（同一 `result_id` 下按 `(level, sector_code)` 唯一） |
| `sector_name` | VARCHAR(128) | N | 板块名称 |
| `parent_sector_code` | VARCHAR(32) | Y | 上一级板块代码（L1 为 null；L2 指向 L1；L3 指向 L2） |
| `sector_stock_count` | INTEGER | N | 板块有效股票数 |
| `sector_top_stock_count` | INTEGER | N | 板块 Top 股票数 |
| `top_density` | NUMERIC(10,6) | N | 上榜密度 |
| `median_return` | NUMERIC(12,6) | Y | 中位收益（`top_count_score` 时可为 null） |
| `momentum_score` | NUMERIC(14,6) | N | 板块动量得分 |
| `small_sample_flag` | BOOLEAN | N | 是否小样本（`sector_stock_count < 5`） |

**索引**：
- `UNIQUE(result_id, level, sector_code)` — 同一次计算同一层级板块唯一
- `(result_id, level, momentum_score DESC)` — 结果表默认按得分倒序
- `(result_id, parent_sector_code)` — **下钻查询主索引**：给定父板块快速拿子板块

**说明**：每次因子计算生成 1 条 `factor_result` + N 条 `factor_result_row`（N = L1/L2/L3 全部板块数之和），均在同一事务写入。

### 7.4 `factor_result_stock` — 每次计算下的个股收益快照

支持 US-7.5 板块股票列表：给定板块，快速拿到所有属于该板块的有效股票及其收益率、是否属全市场 Top 集合。

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `result_id` | BIGINT | N | 外键 → `factor_result.id`（ON DELETE CASCADE） |
| `ts_code` | VARCHAR(16) | N | 股票代码 |
| `stock_name` | VARCHAR(64) | N | 快照时的股票名称 |
| `l1_code` / `l1_name` | VARCHAR(32/128) | Y | 一级板块 code/name |
| `l2_code` / `l2_name` | VARCHAR(32/128) | Y | 二级板块 code/name |
| `l3_code` / `l3_name` | VARCHAR(32/128) | Y | 三级板块 code/name |
| `stock_return` | NUMERIC(14,8) | Y | 个股收益率（`params.return_method` 决定 simple / log；缺前复权价时为 null） |
| `is_top` | BOOLEAN | N | 是否属于全市场 Top 集合 |
| `missing_reason` | VARCHAR(64) | Y | 缺失原因（如 `NO_START_PRICE` / `NO_END_PRICE`）；成功计算时为 null |

**索引**：
- `UNIQUE(result_id, ts_code)` — 同一次计算下每支股票唯一
- `(result_id, l1_code, stock_return DESC)` — L1 板块股票列表默认按收益降序
- `(result_id, l2_code, stock_return DESC)` — L2 板块股票列表默认按收益降序
- `(result_id, l3_code, stock_return DESC)` — L3 板块股票列表默认按收益降序
- `(result_id, is_top)` — 快速统计 Top 集合

**说明**：一次因子计算的持久化事务包含 1 条 `factor_result` + N 条 `factor_result_row` + M 条 `factor_result_stock`（M ≈ 有效股票数，A 股约 5000）；三张表 CASCADE 删除。

### 7.5 失效标记触发路径（跨领域）

| 触发事件 | 影响 | 更新语句 |
| --- | --- | --- |
| SW 快照同步成功 | `industry_snapshot_at` 早于本次同步完成时间的 SW 结果 | `UPDATE factor_result SET stale=true, stale_reason='INDUSTRY_UPDATE', stale_at=now() WHERE classification='SW' AND industry_snapshot_at < <sync_finished_at>` |
| K 线数据变化（补数 / 修数） | v1 保守：不自动标记（避免误伤）；用户重算即可 | 无 |

**说明**：当前申万分类为 Tushare SW2021 快照模型，无版本/回滚表。K 线补数触发失效在 v1 不自动化，用户可手动重算。

---

## 8. 浏览历史

### 8.1 `browse_history` — 页面状态保存

| 字段 | 类型 | Null | 说明 |
| --- | --- | --- | --- |
| `id` | BIGSERIAL | N | 主键 |
| `username` | VARCHAR(64) | N | 用户名 |
| `page_key` | VARCHAR(64) | N | 页面标识（如 `browse:k_line_daily` / `stock_detail:600000.SH`） |
| `page_title` | VARCHAR(255) | N | 页面标题（用户可读） |
| `page_state` | JSONB | N | 页面状态快照（筛选条件 / 字段顺序 / 分页 / 页面级参数） |
| `visited_at` | TIMESTAMPTZ | N | 访问时间 |

**索引**：`(username, visited_at DESC)`；`(username, page_key, visited_at DESC)`
**说明**：v1 保留每用户最近 100 条记录，超过则由业务层裁剪（不做数据库触发器）。

---

## 9. 关键关系图

```
sw_industry_version (1) ──┬── (N) sw_index_classify
                          └── (N) sw_index_member_all
                          └── (N) factor_result   [industry_version_id]

factor_result (1) ──┬── (N) factor_result_row      [result_id, level]
                    └── (N) factor_result_stock    [result_id, ts_code]

stock_basic (1) ── (N) k_line_daily        [ts_code]
stock_basic (1) ── (0..1) latest_market_cap [ts_code]
stock_basic (1) ── (0..1) csrc_industry     [ts_code]
stock_basic (1) ── (N) sw_index_member_all  [ts_code, 跨版本]
```

---

## 10. Alembic 迁移策略

- 首个迁移一次性创建全部核心表 + 索引；后续变更均通过独立 revision（P1 各任务已按此路径推进）
- **禁止**手工修改数据库 schema —— 一切通过 Alembic
- PG 15 + 使用 Alembic 无需 batch mode
- 生产库变更前先在开发库执行 `alembic upgrade head` 验证

---

## 11. 关键约束（一次性汇总）

- 所有业务唯一键都用 `UNIQUE INDEX`，不放主键
- 所有跨表引用都用 `FOREIGN KEY`，删除策略：
  - `factor_result_row.result_id → factor_result.id`：CASCADE
  - `factor_result_stock.result_id → factor_result.id`：CASCADE
  - `sw_index_classify.version_id → sw_industry_version.id`：RESTRICT（版本不能物理删除）
  - `sw_index_member_all.version_id → sw_industry_version.id`：RESTRICT
  - `factor_result.industry_version_id → sw_industry_version.id`：SET NULL（若历史版本被清理）
- `is_current` 部分唯一索引确保同时只有一个申万当前版本
- `data_update_task.task_key` 部分唯一索引确保按日幂等
- 时间字段全部 `TIMESTAMPTZ`，应用层用 UTC 存储、前端展示 `Asia/Shanghai`
- 数值精度：价格 `NUMERIC(12,4)`；量额 `NUMERIC(20,2/4)`；市值 `NUMERIC(20,2)`

---

## 12. ADR 汇总

| ID | 决策 | 章节 |
| --- | --- | --- |
| **ADR-DB01** | 主键统一 BIGSERIAL；业务键作 UNIQUE | §2 |
| **ADR-DB02** | 时间字段全部 TIMESTAMPTZ | §2 |
| **ADR-K01** | K 线事实表只存 raw，复权动态计算，最新 QFQ 单独缓存 | §4.3 |
| **ADR-DB03** | 半结构化字段用 JSONB | §2 |
| **ADR-DB04** | 申万版本生效标识使用 PG 部分唯一索引（`WHERE is_current`） | §5.1 |
| **ADR-DB05** | 申万分类回滚 / 新版本写入自动标记 factor_result 失效；K 线补数不自动标记 | §7.5 |
| **ADR-DB06** | 一次因子计算跨层级落库：1 条 `factor_result` + N 条 `factor_result_row`（含 `level` / `parent_sector_code`）+ M 条 `factor_result_stock`（个股收益快照），同事务写入 | §7.2 ~ §7.4 |
| **ADR-DB07** | 浏览历史每用户保留最近 100 条，业务层裁剪 | §8.1 |
| **ADR-DB08** | 迁移唯一手段是 Alembic；禁止手改 schema | §10 |
| **ADR-DB09** | 数据更新任务通过 `(task_type, task_key)` 部分唯一索引保证按日幂等 | §6.1 |
| **ADR-DB10** | `factor_result.classification` 冗余存储；`factor_result_row.parent_sector_code` 支撑下钻查询；`factor_result_stock` 三级 code 冗余支撑各层级板块股票列表 | §7.2 ~ §7.4 |
| **ADR-DB11** | 所有 Repository 的 `upsert_many` 使用 `core/db.py::chunked` 分批（safety cap 60000 参数），规避 PG 单语句 65535 参数上限 | P1-05 |

---

## 13. 已解决 03 遗留

| 03 遗留项 | 本文档决策 |
| --- | --- |
| K 线复权存法 | ADR-K01：raw 事实表 + 复权因子 + 最新 QFQ 缓存 |
| `factor_result.stale` 字段设计 | §7.2 + §7.4 |
| `latest_market_cap` 表结构 | §4.5 |
| 申万分类三张表关系 | §5 |
| `audit_log` / `error_log` 字段清单 | §3.2 / §3.3 |
| `browse_history.page_state` | §8.1 |

至此 5 份文档全部就绪，待用户批准后进入下一轮计划（prompt 治理 + `06_TASKS.md` 任务清单 + 启动 P1-01）。
