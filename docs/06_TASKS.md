# istock v1 任务清单

> 每个任务颗粒度 = 一次 vibe-coding 会话（AI 30–90 分钟 + 用户 review）。
> **Task ID 一经分配不再改动**（对应 commit / PR / audit）。
> 提交任务时按 `prompt/TASK_TEMPLATE.md` 组装 prompt。

**任务状态**：`pending` / `in_progress` / `blocked` / `done` / `deferred`

---

## Phase 1 · 数据基座（7 任务）

### P1-01 项目骨架 + `/health` 端点
- **状态**：done（本仓库直接执行完成）
- **参考**：`PROJECT.md`、`docs/03_MODULES.md §9`、`docs/04_TECH_STACK.md §9`、`docs/04_TECH_STACK.md §10`
- **交付物**：
  - `backend/{app,alembic,tests}/` 目录结构
  - `backend/app/{api,services,repositories,adapters,factors,core}/`（先建空 `__init__.py`）
  - `backend/app/main.py` — FastAPI 应用组装
  - `backend/app/api/health.py` — `GET /api/health` 返回 envelope
  - `backend/app/core/envelope.py` — `ok()` / `fail()`
  - `backend/pyproject.toml` — 依赖 + Ruff + mypy 配置（uv 管理）
  - `backend/uv.lock` — uv 锁文件
  - `frontend/` — Vite + React + TS + AntD scaffold
  - `frontend/src/main.tsx` + `App.tsx`（先展示 hello world）
  - `README.md` — 本地启动步骤
- **DoD**：
  - [ ] PostgreSQL、后端和前端均可在本机启动
  - [ ] `curl http://localhost:8000/api/health` 返回 `{"success":true,"data":{...},"message":""}`
  - [ ] 前端 `http://localhost:5173` 展示占位页
  - [ ] `ruff check` / `mypy` / `pnpm lint` 全绿
- **Out-of-scope**：不做认证、不做真实业务表、不做定时任务
- **关联用户故事**：无（脚手架任务）

---

### P1-02 PostgreSQL + Alembic + 4 张核心表
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/05_DATA_MODEL.md §4.1-4.3`、`§6.1`、`§10`；`docs/03_MODULES.md §3.3`；`prompt/reference/api_envelope.md`
- **交付物**：
  - `backend/app/core/db.py` — SQLAlchemy engine + Session + UOW
  - `backend/app/models/{stock_basic,trade_calendar,k_line_daily,data_update_task}.py`
  - `backend/app/repositories/{stock_repo,trade_cal_repo,kline_repo,task_log_repo}.py`
  - `backend/alembic/env.py` + `versions/0001_initial.py`
  - `backend/tests/unit/test_repositories.py` — 幂等 upsert / 基础查询
- **DoD**：
  - [ ] `alembic upgrade head` 干净通过
  - [ ] 4 个 Repository 各支持 upsert（PG `ON CONFLICT DO UPDATE`）
  - [ ] 幂等测试：同参数 upsert 两次行数不变
  - [ ] Repository **只暴露领域方法**（不返回 ORM Query）
  - [ ] `ruff` / `mypy` / `pytest` 全绿
- **Out-of-scope**：不做 baostock 同步、不做 API 端点
- **关联用户故事**：US-2.1、US-2.2、US-2.3

---

### P1-03 baostock adapter
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/03_MODULES.md §3.4`；`prompt/reference/baostock_cheatsheet.md`
- **交付物**：
  - `backend/app/adapters/baostock_adapter.py` — `BaostockSession` context manager + `fetch_stock_basic` / `fetch_trade_cal` / `fetch_kline`
  - `backend/app/core/errors.py` — `AdapterConnectionError` / `AdapterDataError` / `AdapterAuthError`
  - `backend/tests/integration/test_baostock_adapter.py` — 真接口打通 1 支样本股
- **DoD**：
  - [ ] `fetch_kline("sh.600000", ...)` 可返回未复权行情
  - [ ] 停牌日行 `trade_status=0` 且价格字段为 null
  - [ ] Adapter **不写数据库**（返回纯数据结构）
  - [ ] 单文件 <200 行
  - [ ] 测试打真接口（用 `@pytest.mark.integration`）
- **Out-of-scope**：不做 Service 编排、不做入库
- **关联用户故事**：US-2.1、US-2.2、US-2.3

---

### P1-04 最新市值 adapter + 合成 service + 决策记录
- **状态**：done（本仓库直接执行完成 —— **两次决策**：初版走 akshare 兜底；实测东财风控不可用后**重做**为 baostock 单源合成）
- **参考**：`docs/04_TECH_STACK.md §4.2`（ADR-16 修订）；`docs/05_DATA_MODEL.md §4.4`；`prompt/reference/baostock_cheatsheet.md §5`
- **交付物**：
  - `backend/app/adapters/baostock_profit.py` — `fetch_profit_data(bs_code, year, quarter)` 返回 `ProfitDataRow | None`
  - `backend/app/adapters/baostock_types.py` — 追加 `ProfitDataRow` DTO
  - `backend/app/models/latest_market_cap.py` — 加 `total_share` / `liqa_share` / `snapshot_close` / `snapshot_date` 字段
  - `backend/alembic/versions/0003_market_cap_from_baostock.py` — 加字段迁移
  - `backend/app/repositories/market_cap_repo.py` — `MarketCapUpsertRow` 扩字段；upsert set_ 覆盖新列
  - `backend/app/services/market_cap_service.py` — 编排 `fetch_profit_data + kline_repo.get(basedate) → 合成 total_share × close → upsert`；缺任一侧标 `baostock_missing`
  - `backend/tests/unit/test_baostock_profit.py` — 4 tests（空 rs / 错误码 / 空 totalShare）
  - `backend/tests/unit/test_market_cap_service.py` — 2 tests（`_bs_code_from_ts` / `_quarter_of` 边界）
  - `backend/tests/integration/test_market_cap_service.py` — 5 tests（happy / profit 缺 / K 线缺 / 幂等 / adapter 异常吞噬）
  - `backend/tests/integration/test_baostock_adapter.py` — 追加 `test_fetch_profit_data_returns_total_share`（真接口）
  - `backend/tests/integration/test_market_cap_repo.py` — 字段值改为 `baostock_synth` / `baostock_missing`
  - **ADR-06 与 ADR-16 修订**（04_TECH_STACK §11）
  - `pyproject.toml` — 移除 `akshare>=1.12` 依赖
- **DoD**：
  - [x] baostock `query_profit_data` 真接口打通样本股
  - [x] `total_share × close_raw` 合成成功；`total_market_cap` 值符合真实市场量级（如浦发 293 亿股 × 10 元 ≈ 2935 亿）
  - [x] profit 缺失（BJ 部分）或 K 线缺失时 `market_cap_source='baostock_missing'`；service 不因单支异常中断整批
  - [x] Repository upsert 幂等；扩字段成功入库
  - [x] `pytest` 40 passed；`ruff check` 全绿
- **Out-of-scope**：不做同步 Service 定时调度（P2-03）；不做前端；不做历史市值
- **关联用户故事**：US-2.4

---

### P1-05 stock_basic + trade_cal 同步 Service
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/03_MODULES.md §3.2`；`docs/05_DATA_MODEL.md §4.1-4.2、§6.1`
- **交付物**：
  - `backend/app/services/sync_basic_service.py` — 编排 stock_basic + trade_cal 全量刷新
  - `backend/tests/integration/test_sync_basic_service.py`
- **DoD**：
  - [ ] 首次跑：全市场 stock_basic 落库；`trade_calendar` 覆盖近 3 年 + 至次年年底
  - [ ] 二次跑：相同数据不产生重复行，`updated_at` 刷新
  - [ ] 每次跑生成 `data_update_task` 行（`SUCCESS` / `FAILED`）
  - [ ] `data_update_task.task_key` 幂等约束生效（同日重复调用识别为已完成）
- **Out-of-scope**：不做 K 线、不做 API、不做 scheduler
- **关联用户故事**：US-2.1

---

### P1-06 K 线同步 Service（历史任务，现已收敛为 raw）
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/03_MODULES.md §3.2`；`docs/05_DATA_MODEL.md §4.3`；`prompt/reference/baostock_cheatsheet.md`
- **交付物**：
  - `backend/app/services/sync_kline_service.py` — 编排三次 baostock 调用 + 合并为 `k_line_daily` 一行 3 组字段
  - `backend/tests/integration/test_sync_kline_service.py`（20 支 × 5 天）
- **DoD**：
  - [ ] 20 支样本股 × 5 天未复权 K 线成功入库
  - [ ] `trade_status=0` 的停牌日行价格字段为 null
  - [ ] 幂等：重复同步同一区间不产生冲突
  - [ ] 生成 `data_update_task` 记录（`expected_count / success_count / missing_count / error_count` 全部有值）
  - [ ] 单文件 <400 行；若接近上限先拆
- **Out-of-scope**：不覆盖全市场（全市场跑由 scheduler 触发）、不做 API
- **关联用户故事**：US-2.1、US-2.2、US-2.3

---

### P1-07 数据健康 API v0
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/02_USER_STORIES.md#US-3.1`；`docs/03_MODULES.md §3.1、§3.2`；`prompt/reference/api_envelope.md`
- **交付物**：
  - `backend/app/api/health.py` — `GET /api/health/summary`
  - `backend/app/services/health_service.py` — `get_summary()` 聚合各表最新时间 + 行数
  - `backend/tests/integration/test_health_api.py` — contract test
- **DoD**：
  - [ ] `GET /api/health/summary` 返回：`{stock_basic:{count,last_updated}, trade_calendar:{...}, k_line_daily:{...}, latest_market_cap:{...}}`
  - [ ] envelope 合规
  - [ ] 空表场景 `count=0`、`last_updated=null`
  - [ ] contract test 覆盖 200 / 空数据 / 未登录
- **Out-of-scope**：不做月历、不做单日详情、不做前端
- **关联用户故事**：US-3.1

---

## Phase 2 · 数据健康（6 任务）

### P2-01 K 线月历数据 Service
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/02_USER_STORIES.md#US-3.2`；`docs/05_DATA_MODEL.md §4.2、§4.3`
- **交付物**：
  - `backend/app/services/health_calendar_service.py` — `get_calendar(year, month, trade_cal_repo, stock_repo, kline_repo)` 返回 `CalendarMonth`（覆盖整月每一天）
  - `backend/app/repositories/kline_repo.py` — 新增 `distinct_stock_counts_by_date_range(start, end)` / `anomaly_dates_in_range(start, end)`
  - `backend/app/repositories/stock_repo.py` — 新增 `count_active_at(day)`（`is_common AND list_date<=day AND (delist_date IS NULL OR >day)`）
  - `backend/tests/unit/test_health_calendar.py` — 9 tests 覆盖 US-3.2 全部 EARS + 跨月边界 + 无参数校验
- **DoD**：
  - [x] 完整交易日返回 `green`（`actual == expected`）
  - [x] 部分股票缺失返回 `yellow`（`0 < actual < expected`）
  - [x] 全部缺失返回 `red`（`actual == 0`）
  - [x] 非交易日返回 `gray`（`is_open=False`；无论 K 线是否有行）
  - [x] 异常图标：`has_anomaly` 独立 flag（`trade_status != 0 AND close_raw IS NULL`；停牌行 `trade_status=0` 不算异常）
  - [x] 边界：跨月首末日均出现在返回集；早期无活跃股票宇宙返回 `gray` 而非 `red`
  - [x] `pytest tests/unit/test_health_calendar.py` 9 passed；全套 unit 41 passed；`ruff check` 全绿
- **Out-of-scope**：不做 API 端点（P2-04）；不做前端；不做 baostock 真接口调用（Service 只读 DB）
- **关联用户故事**：US-3.2

---

### P2-02 单日健康详情 Service
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/02_USER_STORIES.md#US-3.3`；`docs/05_DATA_MODEL.md §6.1`
- **交付物**：
  - `backend/app/services/health_day_service.py` — `get_day_detail(day, ...)` 返回 `DayDetail`（expected/success/missing/error 计数 + 缺失/异常 ts_code 列表 capped 100 + 覆盖该日的最近 SYNC_KLINE 任务摘要）
  - `backend/app/core/errors.py` — 新增 `NotFoundError`（API 层映射 404 / `NOT_FOUND_TRADING_DAY`）
  - `backend/app/repositories/kline_repo.py` — 新增 `ts_codes_on(day)` / `anomaly_ts_codes_on(day)`
  - `backend/app/repositories/stock_repo.py` — 新增 `list_active_ts_codes_at(day)`
  - `backend/tests/unit/test_health_day.py` — 8 tests
- **DoD**：
  - [x] 数据源为 `data_update_task` + `k_line_daily` + `stock_basic` 交叉计算（不完全依赖 task 记录）
  - [x] 缺失股票列表可导出（`missing_ts_codes` 按 `ts_code` 升序，capped 100）
  - [x] 异常股票列表可导出（`error_ts_codes` 同上；异常 = 已入库行 AND `trade_status!=0` AND `close_raw IS NULL`）
  - [x] 非交易日抛 `NotFoundError`（API 层映射 `NOT_FOUND_TRADING_DAY`）
  - [x] 覆盖该日的最近 SYNC_KLINE 任务摘要（`task_key=SYNC_KLINE:today:start:end` 解析 `[start,end]` 覆盖判定）；不覆盖或格式错误 → 三字段为 None
  - [x] `pytest tests/unit/test_health_day.py` 8 passed；全套 unit 49 passed；`ruff check` 全绿
- **Out-of-scope**：不做 API 端点（P2-04）；不做前端；不做跨股票详情跳转（前端 P2-06）
- **关联用户故事**：US-3.3

---

### P2-03 定时任务调度
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/03_MODULES.md §3.2 (scheduler)`；`docs/04_TECH_STACK.md §2 (APScheduler)`；`PROJECT.md §11.5`（baostock 预算）
- **交付物**：
  - `backend/app/services/scheduler.py` — `run_daily_sync(today, session_factory)` 编排四步 + `build_scheduler()` 返回可选 AsyncIOScheduler + `main()` CLI 入口
  - `backend/app/core/config.py` — 新增 `SCHEDULER_ENABLED / SCHEDULER_HOUR / SCHEDULER_MINUTE / SCHEDULER_TRIGGERED_BY` 环境变量（`SCHEDULER_ENABLED` 默认 `false`）
  - `backend/app/main.py` — FastAPI `lifespan` 集成 scheduler 生命周期（默认关，不影响本地/CI）
  - `backend/tests/unit/test_scheduler.py` — 10 tests
- **DoD**：
  - [x] 单进程一个 `baostock_session()` 复用于四步：`sync_stock_basic → sync_trade_calendar → sync_kline (today) → market_cap`
  - [x] 每步独立 try/except：某步失败不阻塞后续；`DailySyncReport.steps[step] ∈ {SUCCESS, FAILED, SKIPPED}`
  - [x] `AdapterQuotaExceededError` 中止后续步骤（`report.quota_exhausted=True`）
  - [x] `sync_kline` 非交易日 / 空活跃股 → `SKIPPED`
  - [x] `market_cap` 只在**季末月**（3/6/9/12）交易日运行；其他日 `SKIPPED`（避免每天 5000 次 profit_data）
  - [x] 每步内部服务自行写 `data_update_task`（沿用 P1-05/P1-06 已有逻辑）
  - [x] `SCHEDULER_ENABLED=false`（默认）→ `build_scheduler()` 返回 None，FastAPI 启动不启 scheduler
  - [x] `python -m app.services.scheduler` CLI 手工触发一次全链路
  - [x] `pytest tests/unit/test_scheduler.py` 10 passed；全套 unit 59 passed；`ruff check` 全绿
- **Out-of-scope**：不做失败告警（v1 只 log）；不做前端；不做集成测试对真 baostock（受 §11.5 预算约束，仅提供 CLI 手工触发）
- **关联用户故事**：US-2.1、US-3.4

---

### P2-04 健康 API 完整版
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/02_USER_STORIES.md#US-3.2 到 #US-3.4`；`prompt/reference/api_envelope.md`
- **交付物**：
  - `backend/app/api/health.py` 追加：
    - `GET /api/health/kline/calendar?year=&month=` → 调 P2-01 `get_calendar`
    - `GET /api/health/kline/day/{date}` → 调 P2-02 `get_day_detail`
    - `GET /api/health/tasks?page=&page_size=&order_by=&order=` → 调 `TaskLogRepo.list_paged`
  - `backend/app/repositories/task_log_repo.py` — 新增 `list_paged(page, page_size, order_by, order)` + `ORDER_FIELDS` whitelist
  - `backend/app/core/errors.py` — 新增 `ValidationError`（携带 `code` / `detail`）
  - `backend/app/main.py` — 注册 3 个 exception handler：`NotFoundError` / `ValidationError` / `RequestValidationError` → 统一 envelope
  - `backend/tests/unit/test_health_api_full.py` — 11 contract tests（无 DB，用 dependency_overrides + service mock）
  - `backend/tests/integration/test_health_api_full.py` — 5 integration tests（真 PG）
- **DoD**：
  - [x] 3 个新端点 envelope 合规（`{success, data, message}`）
  - [x] 分页：`?page=1&page_size=50`；`page_size > 200` → `VALIDATION_PAGE_SIZE_TOO_LARGE`
  - [x] 排序：`?order_by=started_at&order=desc`；非 whitelist → `VALIDATION_INVALID_ORDER_FIELD`；`order` 只允许 `asc`/`desc`
  - [x] 参数校验：`year/month` 越界、`day` 格式错误、缺失必填 → 全部走 envelope（不返 422）
  - [x] `NotFoundError`（非交易日）→ `NOT_FOUND_TRADING_DAY` 200 + envelope
  - [x] Contract test 覆盖成功 + 参数错误 + 非交易日
  - [x] 全套 unit 70 passed；`ruff check` 全绿
- **Out-of-scope**：不做前端；不做鉴权（P2-05）；不做 filters（复杂筛选 Phase 3 再上）
- **关联用户故事**：US-3.2、US-3.3、US-3.4

---

### P2-05 前端脚手架 + 登录桩 + AntD 布局
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/03_MODULES.md §5`；`docs/04_TECH_STACK.md §5`、`§8.1`；`prompt/reference/api_envelope.md`
- **交付物**：
  - `frontend/src/api/http.ts` — axios 实例 + 请求拦截器（`X-User` 自动注入）+ 响应拦截器（envelope 解包，抛 `EnvelopeError` / `NetworkError`）+ `apiGet` / `apiPost`
  - `frontend/src/api/auth.ts` — `listPreconfiguredUsers()`（v1 桩）
  - `frontend/src/api/health.ts` — `getSummary` / `getCalendar` / `getDayDetail` / `getTasks`（TS 契约与后端 P2-04 对齐）
  - `frontend/src/store/authStore.ts` — Zustand user state + `persist(localStorage)`
  - `frontend/src/pages/LoginPage.tsx` — 用户下拉 + 登录按钮
  - `frontend/src/components/AppLayout.tsx` — 顶栏（当前用户 + 退出）+ 侧栏（Dashboard / 数据浏览占位）+ Outlet 内容区
  - `frontend/src/components/AdminPasswordModal.tsx` — 敏感操作密码弹窗（占位实现）
  - `frontend/src/pages/DashboardPage.tsx` — Dashboard 占位（下任务 P2-06 实现真数据）
  - `frontend/src/router.tsx` — 路由 + `<RequireAuth>` 守卫
  - `frontend/src/main.tsx` — 装配 `QueryClientProvider` + `BrowserRouter` + `ConfigProvider(zhCN)`
  - `frontend/.eslintrc.cjs` — 补齐 ESLint 配置（原缺失导致 `npm run lint` 报错）
- **DoD**：
  - [x] 打开首页 → 未登录跳 `/login`（`RequireAuth` 检测 `authStore.user==null`）
  - [x] 登录后进入 `/`（Dashboard 占位页）
  - [x] 所有 API 请求自动带 `X-User`（`http.ts` 请求拦截器）
  - [x] AntD 主题正确加载（zh_CN），无 console.error（`react-router-dom` v6 + `<BrowserRouter>`）
  - [x] `npm run typecheck` 无错；`npm run lint` 全绿；`npm run build` 成功产出
- **Out-of-scope**：不做真实 Dashboard 内容（P2-06）；不做密码 sha256 校验（P2-06 之后）
- **关联用户故事**：US-1.1、US-1.2、US-1.4（弹窗占位）

---

### P2-06 Dashboard 页面（真数据）
- **状态**：done（本仓库直接执行完成）
- **参考**：`docs/02_USER_STORIES.md#US-3.1 到 #US-3.4`；`docs/03_MODULES.md §5.1`
- **交付物**：
  - `frontend/src/pages/DashboardPage.tsx` — 装配 SummaryCards + KlineCalendar + TasksTable
  - `frontend/src/components/SummaryCards.tsx` — 4 张状态卡（stock_basic / trade_calendar / k_line_daily / latest_market_cap）+ latest_task 摘要，接 `/api/health/summary`
  - `frontend/src/components/KlineCalendar.tsx` — ECharts calendar heatmap，月切换、状态色映射、异常图标、点击跳转
  - `frontend/src/components/TasksTable.tsx` — AntD Table，分页 + 排序（whitelist：`started_at / finished_at / task_type / status`），接 `/api/health/tasks`
  - `frontend/src/pages/KlineDayDetailPage.tsx` — 路由 `/day/:date`，接 `/api/health/kline/day/{date}`；NOT_FOUND_TRADING_DAY 显示 Alert 提示
  - `frontend/src/router.tsx` — 新增 `/day/:date` 路由
  - `frontend/package.json` — 追加 `echarts` / `echarts-for-react` 依赖
- **DoD**：
  - [x] Dashboard 展示 4 张核心状态卡（stock_basic / trade_cal / k_line_daily / latest_market_cap）+ 最近任务摘要
  - [x] K 线月历支持月份切换（左右箭头 + DatePicker）+ 颜色状态（green/yellow/red/gray）+ 异常图标（⚠）
  - [x] 点击月历某日（限交易日）跳转 `/day/:date` 单日详情页
  - [x] 任务日志表分页（默认 20，可选 10/20/50/100）+ 排序（后端 whitelist 字段）
  - [x] **接真后端 API，不用 mock**（React Query + envelope 解包）
  - [x] `npm run typecheck / lint / build` 全绿
- **Out-of-scope**：不做数据浏览（Phase 3）、不做股票详情（Phase 3）
- **关联用户故事**：US-3.1、US-3.2、US-3.3、US-3.4

---

## 后续 Phase（待 Phase 1+2 完成后规划）

- **Phase 3 · 数据浏览** — done（本仓库直接执行完成）：数据表列表、通用表浏览、字段控制、浏览历史、股票详情
- **Phase 4 · 申万分类维护** — 上传 / 解析 / 校验 / 预览 / 写入 / 版本 / 回滚
- **Phase 5 · 板块动量因子** — done（本仓库直接执行完成）：SW2021 因子计算 / 参数配置 / 结果落库 / 下钻 / 结果失效
- **Phase 6 · 体验完善** — 异常日志、添加用户、UI 打磨

**规划节奏**：Phase 1 完成后再写 Phase 3 任务；避免过度设计。

---

## 依赖关系图

```
P1-01 (骨架)
  ↓
P1-02 (DB + 表) ──┐
                  ↓
P1-03 (baostock) → P1-05 (基础同步) → P1-07 (健康 API v0)
                  ↓                      ↓
P1-04 (baostock_profit 合成) → P1-06 (K 线同步) ──┘

Phase 2:
P1-07 → P2-01 (月历 Service) ──┐
        P2-02 (单日 Service) ─→ P2-04 (健康 API 完整版) ──┐
        P2-03 (Scheduler) ──────────────────────────────→ P2-06 (Dashboard)
                                                          ↑
                                                    P2-05 (前端脚手架)
```

---

## 提交任务的检查清单

在提交任务给 AI 之前，检查：

- [ ] Task ID 存在于本文件且状态为 `pending`
- [ ] 已按 `prompt/TASK_TEMPLATE.md` 填空
- [ ] 参考文档列出**具体锚点**，不是"看整份文档"
- [ ] DoD 每一项**可测**
- [ ] Out-of-scope 显式列出（防止 AI 越权）
- [ ] `prompt/CONTEXT.md` 全文作为前置

任务完成后：

- [ ] 运行 DoD 中的所有检查项
- [ ] 更新本文件的任务状态为 `done`
- [ ] 若 DoD 有一项没过，标 `blocked` 并写清阻塞原因
- [ ] 修改到表结构时同步更新 `docs/05_DATA_MODEL.md`
