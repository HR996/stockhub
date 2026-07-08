# A 股量化分析工具 v1 - AI Project PRD

## 1. 项目目标

本项目旨在开发一个面向少量用户的 A 股量化分析 Web 系统。

系统维护一套共享的 A 股基础数据，并提供：

* 数据健康状态查看
* 数据浏览
* 股票详情查看
* 行业分类维护
* 板块级动量因子分析

v1 的重点不是交易系统，而是建立一套稳定、可扩展的数据分析平台。

---

# 2. 开发原则

## 2.1 MVP 优先

每个阶段必须形成可运行版本。

禁止一次实现全部功能。

---

## 2.2 数据优先

所有业务均建立在统一的数据基座之上。

数据基座必须先完成，再开发业务功能。

---

## 2.3 API First

所有页面必须通过公开 API 获取数据。

页面不得直接访问数据库。

---

## 2.4 后端与前端解耦

后端仅负责：

* 数据维护
* 数据查询
* 因子计算
* 状态管理

前端仅负责：

* 页面展示
* 参数输入
* 用户交互

---

## 2.5 可维护优先

禁止：

* 巨型 Service
* 巨型 Controller
* 超过 500 行的单文件
* 页面直接拼 SQL
* 页面直接计算因子

---

# 3. 开发阶段

整个项目分六个阶段完成。

---

# Phase 1：数据基座

目标：

建立统一的数据源适配层和本地数据仓库。

完成后应具备：

* 股票基础信息同步
* 交易日历同步
* 日 K 线同步
* 最新市值同步
* 证监会行业同步
* 数据版本记录

本阶段不开发复杂页面。

仅提供：

* Dashboard
* 数据健康 API

---

交付：

```text
数据源
↓

Adapter

↓

Repository

↓

Database

↓

Health API
```

---

# Phase 2：数据健康

目标：

完成数据维护能力。

包括：

* 更新任务
* 更新日志
* 数据完整性检查
* K 线月历
* 单日健康详情

完成后：

Dashboard 能完整展示数据状态。

---

# Phase 3：数据浏览

目标：

实现数据库浏览体验。

包括：

* 数据表列表
* 数据浏览
* 分页
* 排序
* 筛选
* 字段说明
* 股票详情

本阶段形成完整的数据浏览能力。

---

# Phase 4：行业分类维护

目标：

完成申万行业维护。

包括：

* 上传
* 校验
* 预览
* 更新
* 版本记录
* 回滚

完成后：

系统可以维护 SW 一级、二级、三级行业。

---

# Phase 5：板块动量因子

目标：

完成板块动量计算。

支持：

参数配置：

* basedate
* window
* top_ratio
* classification
* level
* return_method
* score_method

return_method：

```text
simple
log
```

score_method：

```text
median_return_score

top_count_score
```

计算结果支持：

* 排序
* 筛选
* 配置保存
* 配置复制
* 配置删除

---

# Phase 6：体验完善

包括：

* 浏览历史
* 页面状态恢复
* 操作日志
* 异常日志
* 添加用户
* 整体 UI 优化

---

# 4. 数据架构

```
                数据源

      TuShare / 手工上传 SW

                 │

          Source Adapter

                 │

        Data Repository

                 │

           SQLite / DuckDB

                 │

      ┌──────────┴──────────┐

 Update Service       Query Service

      │                    │

      └──────────┬──────────┘

             REST API

                 │

              Frontend
```

---

# 5. API 原则

所有页面只能调用 REST API。

API 返回：

```json
{
    "success": true,
    "data": {},
    "message": ""
}
```

统一：

* 分页格式
* 排序格式
* 错误格式
* 时间格式

---

# 6. 页面开发原则

每完成一个页面：

必须完成：

* API
* Mock 数据
* 页面
* 测试

禁止：

页面完成后再补接口。

---

# 7. 数据设计原则

所有业务数据均存放在统一数据库。

禁止：

* 页面缓存业务数据
* 页面重复计算
* 重复维护宽表

所有派生数据：

必须记录：

* 来源版本
* 创建时间
* 创建用户

支持：

失效标记。

---

# 8. 因子设计原则

所有因子：

统一：

```text
参数

↓

读取数据

↓

过滤股票池

↓

计算个股收益

↓

行业聚合

↓

生成结果

↓

保存结果
```

任何因子：

不得直接操作数据库。

统一通过 Repository 获取数据。

---

# 9. 前端原则

前端：

只负责：

* 展示
* 参数输入
* 图表
* 表格

禁止：

* SQL
* 因子计算
* 数据清洗

---

# 10. 日志原则

记录：

* 用户
* 时间
* 操作
* 参数
* 结果

敏感操作：

增加：

* 管理员密码验证
* 二次确认

---

# 11. 技术原则

优先：

* 简单
* 清晰
* 可维护

避免：

* 过度设计
* 微服务
* DDD
* CQRS
* Event Sourcing

本项目属于单机分析工具，不追求高并发。

---

# 11.5 baostock 调用预算（硬约束）

**baostock 单账号 5 万次 / 日 调用上限**。触顶后所有接口返回 `10001007 用户请求次数超过限制`，当日无法恢复。所有开发、测试、生产同步均在同一预算内共享。

## 生产日常预算（参考）

| 场景 | 次数 |
| --- | --- |
| `sync_stock_basic` 全市场 | 1 / 日 |
| `sync_trade_calendar` | 1 / 日 |
| `sync_kline` 全市场增量（每股 3 次复权） | ≈ 5000 × 3 = 15000 / 日 |
| `market_cap` 合成（每股 profit_data） | ≈ 5000 / 日（可降为季度刷） |
| **合计** | **≈ 2 万 / 日**（占预算 40%，剩余 3 万供开发/测试/回补） |

## 硬规则

1. **禁止按日循环调用 K 线**：`fetch_kline` 必须传日期区间，一次拿多天。禁止在外层 `for day in trading_days: fetch_kline(..., day, day)` —— 3 年 × 5000 支 × 3 复权 = 1125 万次，秒杀预算。
2. **禁止同一 (code, start, end, adjustflag) 在同一次运行内重复调用**：Service 层需自查逻辑不产生重复请求。
3. **profit_data 只在需要时刷**：`totalShare` 季度更新，非交易日或非月/季末**不必**跑 `market_cap_service` 全量；日常增量只重算受当日 K 线影响的市值。
4. **集成测试样本上限**：默认 ≤ 20 支样本股 × ≤ 10 交易日；禁止无标注地对全市场发真接口测试。若必须全市场（如 `test_sync_stock_basic_full_market`），单个 pytest run 内**只能出现一次**，且不得写"idempotent 重跑第二次真接口"—— 幂等性用 mock 或已缓存数据验证。
5. **单元测试禁真接口**：`tests/unit/**` 一律 mock `bs.query_*` 或 `fetch_*`；只有 `tests/integration/**` 且被 `pytest.mark.integration` 标注的用例可以真调。
6. **CI 默认跳过 integration**：`pytest -m "not integration"` 是默认命令；integration 只在人工触发或每日一次的定时任务里跑。
7. **开发期反复调试**：本地缓存 baostock 返回值（如 `tests/fixtures/*.json` / DuckDB 快照），迭代时改用离线数据，**只在最后打通阶段跑一次真接口**。
8. **登录复用**：`bs_session` fixture 已 session-scope 复用一次登录 —— 禁止在测试或生产循环里反复 `bs.login() / bs.logout()`（每次登录本身就是一次调用）。
9. **失败重试上限 = 1**：Service 层遇 `AdapterConnectionError` 只重试 1 次；禁止指数退避多轮。
10. **触顶降级**：捕获 `error_code=10001007` 时立即中止批量任务、写 `data_update_task.status=FAILED`、发出告警；**不得继续消耗剩余预算**。

## AI 开发期自检清单

每次改动 `adapters/` 或 `services/sync_*` 前必须回答：

- 这次改动会新增多少 baostock 调用？（估算次数）
- 集成测试新增几条真接口用例？累计单 run 是否 ≤ 100 次？
- 是否可以用 mock / fixture / 已入库数据替代？

如果单次 pytest 全套预计 > 200 次真调用，**必须先拆分或改 mock 再提交**。

---

# 12. AI 开发规范

AI 每次只完成一个 Task。

每个 Task 必须：

1. 修改代码；
2. 补充测试；
3. 更新 README；
4. 不修改无关模块；
5. 保持已有接口兼容；
6. 不主动重构整个项目。

如果发现设计问题：

优先提出建议，

不得自行改变架构。

---

# 13. 项目文档结构

```
docs/

01_REQUIREMENTS.md
02_ARCHITECTURE.md
03_DATA_MODEL.md
04_API_SPEC.md
05_UI_SPEC.md
06_FACTOR_DESIGN.md
07_TASKS.md
```

所有开发均以文档为准。

禁止 AI 自行扩展需求或添加未定义功能。
