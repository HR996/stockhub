# Tushare 数据源迁移与数据服务拆分计划

## Summary

将后端所有数据初始化、更新、行情与行业同步统一迁移到 Tushare，保留现有数据库表、后端查询 API、前端展示契约不变。前端仍读取 `stock_basic`、`trade_calendar`、`k_line_daily`、`latest_market_cap`、`sw_industry_*` 等现有表，数据层在写入前完成字段映射、单位转换、停牌补行和复权价计算。

默认选择：

- 继续兼容现有表结构和前端接口，不重做前端数据模型。
- qfq/hfq 自行用 Tushare `daily + adj_factor` 计算，不用 `pro_bar` 作为主链路。
- 数据初始化和更新提取为同仓库独立 worker/service，FastAPI 只负责查询和任务入口。
- 日 K 使用 `trade_date` 维度批量拉取全市场数据，避免按股票逐只请求。

依据：

- Tushare `daily` 支持按 `trade_date` 获取当日全市场日线，并建议按日期循环获取全量历史；停牌期间不提供行情数据。来源：https://tushare.pro/wctapi/documents/27.md
- Tushare `pro_bar` 支持 `qfq/hfq`，但以单只 `ts_code` 为入口；其源码显示复权基于 `daily + adj_factor` 计算。来源：https://tushare.pro/wctapi/documents/109.md ，https://github.com/waditu/tushare/blob/master/tushare/pro/data_pro.py
- Tushare `daily_basic` 提供 `total_mv/circ_mv`，单位为万元，单次最多 6000 条，可按日期循环。来源：https://tushare.pro/wctapi/documents/32.md

## Key Changes

### 1. 数据适配与前端一致性

- 新增 Tushare adapter，覆盖 `stock_basic`、`trade_cal`、`daily`、`daily_basic`、`adj_factor`、`index_classify/index_member` 或当前 SW 行业接口。
- 保留现有业务表作为 canonical model：
  - `stock_basic`：由 Tushare 股票基础信息写入，补齐 `bs_code`、`is_bj`、`is_common`、`is_st` 等兼容字段。
  - `trade_calendar`：由 Tushare `trade_cal` 写入，统一日期格式为现有 `date` 类型。
  - `k_line_daily`：继续保存 raw/qfq/hfq 三组价格列。
  - `latest_market_cap`：改由 `daily_basic.total_mv/circ_mv` 写入，万元转元；股本字段万股转股。
  - `sw_industry_classify`、`sw_industry_member`：继续使用现有 SW 快照模型。
- 单位统一：
  - Tushare `vol` 按“手”返回，写入前乘以 100，统一为股。
  - Tushare `amount` 按“千元”返回，写入前乘以 1000，统一为元。
  - `daily_basic.total_mv/circ_mv` 万元转元。
  - `daily_basic.total_share/float_share/free_share` 万股转股。
- 停牌兼容：
  - 因 Tushare 日线停牌日不返回行，数据服务在全市场日线成功拉取后，对当日交易日内“应存在但缺失”的 active stock 生成 `trade_status=0` 的占位行。
  - 占位行价格、成交量、成交额、换手率为空；股票详情和数据浏览仍能看到该交易日状态。
- ST 兼容：
  - v1 使用股票名称中的 `ST/*ST` 和 `stock_basic.is_st` 派生 `is_st_row`。
  - 不在本轮引入历史名称变更表；后续如因因子过滤需要更严格历史 ST，可再接入 Tushare `namechange`。

### 2. qfq/hfq 计算方案

- 新增本地复权因子表，例如 `stock_adj_factor`：
  - 唯一键：`ts_code + trade_date`
  - 字段：`adj_factor`、`source='tushare'`、`updated_at`
- 日线写入流程：
  - 先写 raw 行情。
  - 同步并保存同日 `adj_factor`。
  - 根据本地 raw 行情和复权因子回填 `open_qfq/high_qfq/low_qfq/close_qfq/preclose_qfq` 与 `open_hfq/...`。
- 复权公式与 Tushare `pro_bar` 保持一致：
  - `hfq_price = raw_price * adj_factor`
  - `qfq_price = raw_price * adj_factor / latest_adj_factor`
  - `latest_adj_factor` 使用该股票当前本地最新交易日的复权因子。
- 由于 qfq 会随最新复权因子变化，任何新增或变更 `adj_factor` 后，数据服务重算该股票本地保留区间内的 qfq/hfq 列。
- `pro_bar` 只作为人工校验或测试参考，不作为主同步链路，避免按股票逐只拉取导致初始化慢。

### 3. 独立数据服务

- 新增同仓库独立数据服务模块，例如 `backend/app/data_service/`：
  - `runner.py`：CLI 入口。
  - `jobs.py`：初始化、增量更新、行业同步任务编排。
  - `tushare_pipeline.py`：Tushare 拉取、映射、入库、复权重算。
- CLI 约定：
  - `python -m app.data_service init --start YYYY-MM-DD --end YYYY-MM-DD`
  - `python -m app.data_service update --date YYYY-MM-DD`
  - `python -m app.data_service sync-sw`
  - `python -m app.data_service recompute-adjusted --start YYYY-MM-DD --end YYYY-MM-DD`
- FastAPI 不再直接承担数据初始化逻辑；原有脚本保留为 thin wrapper 或标记 deprecated，内部调用新 data service。
- `data_update_task` 继续作为任务状态表，新增任务类型：
  - `TUSHARE_INIT`
  - `TUSHARE_UPDATE_DAILY`
  - `TUSHARE_SYNC_BASIC`
  - `TUSHARE_SYNC_SW`
  - `TUSHARE_RECOMPUTE_ADJUSTED`
- 后续可在 Docker Compose 中把 data service 独立成 `data-worker` 进程；本轮先完成代码边界拆分，不强制拆仓库。

### 4. 批量日 K 拉取流程

- 初始化和增量更新都按交易日循环，而不是按股票循环：
  - 读取 `trade_calendar` 中 open days。
  - 对每个 `trade_date` 拉取全市场 `daily`。
  - 同日拉取全市场 `daily_basic`。
  - 同日拉取全市场 `adj_factor`。
  - 三者按 `ts_code + trade_date` merge 后批量 upsert。
- 对 Tushare 单次返回上限做分页防御：
  - 如果返回条数达到接口上限，自动用分页或补充请求继续拉取。
  - 每个交易日的 raw/daily_basic/adj_factor 任一失败，该日期任务标记失败，不生成停牌占位行。
- 两个月测试数据初始化推荐命令：
  - `python -m app.data_service init --start 2026-05-08 --end 2026-07-08`
- 因子计算继续读取 `k_line_daily.close_qfq`，无需改前端和因子 API。

## Test Plan

- 单元测试：
  - Tushare 字段映射、日期格式、`bs_code` 派生、BJ/ST/common stock 判定。
  - `vol`、`amount`、市值、股本单位转换。
  - 停牌占位行生成逻辑。
  - qfq/hfq 公式、最新复权因子变化后的历史重算。
  - Tushare 分页、限流、重试、失败任务状态。
- 集成测试：
  - 用 mock Tushare client 初始化 2 个交易日、3 只股票，验证现有表完整写入。
  - 缺失某只股票当日日线时生成 `trade_status=0`。
  - `daily_basic` 写入 `latest_market_cap` 后，因子计算不再依赖 Baostock。
  - `/api/browse`、`/api/stocks/{ts_code}`、`/api/factor/results` 返回结构保持兼容。
- 真实数据 smoke test：
  - 有 `TUSHARE_TOKEN` 时跑最近 5 个交易日初始化。
  - 校验 raw 行数、qfq/hfq 非空率、市值非空率、SW member 覆盖率。
  - 不在普通 CI 中访问真实 Tushare。
- 前端回归：
  - 数据浏览能看到 `stock_basic`、`k_line_daily`、`latest_market_cap`。
  - 股票详情 raw/qfq/hfq 切换正常。
  - 因子计算使用 qfq 数据能产出结果。
  - stale SW 行业结果提示逻辑不变。

## Assumptions

- 本轮迁移后 Baostock 不再作为默认数据源；旧 adapter 暂时保留用于回滚或对照测试。
- 前端表格、股票详情、因子页面的 API response envelope 不变。
- `daily_basic` 权限足够可用；如果 token 无权限，初始化任务应明确报错 `TUSHARE_PERMISSION_DENIED`，而不是静默写空数据。
- qfq 采用“当前本地最新交易日复权因子”为锚点，因此新增未来数据后会重算历史 qfq，这是预期行为。
- 历史 ST 精准追溯不在本轮实现，v1 只保证字段兼容和当前过滤可用。
