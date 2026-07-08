# istock — vibe-coding 任务模板

> 复制以下模板，填空后与 `prompt/CONTEXT.md` 一起提交给 AI。
> 目标：让每次会话都拿到"最少但足够"的上下文。

---

## 使用方法

组装 prompt 的公式：

```
【前置】prompt/CONTEXT.md 全文
【正文】填好的本模板
【要读的文档】明确列出 Read: docs/NN_*.md#锚点
```

**禁止**：把 01/02/05 全文粘进 prompt。用路径 + 锚点引用即可。

---

## 模板

```markdown
# 任务：<Task ID> — <一句话目标>

## Phase
<Phase 1 数据基座 | Phase 2 数据健康 | ...>

## 参考文档（AI 必读）
- docs/03_MODULES.md#3.3-Repository层
- docs/05_DATA_MODEL.md#4.1-stock_basic
- prompt/reference/baostock_cheatsheet.md
- （其他相关锚点）

## 关联用户故事
US-x.y（列出本任务实现或部分实现的用户故事编号）

## 交付物（文件清单）
- backend/app/models/stock_basic.py（新建）
- backend/app/repositories/stock_repo.py（新建）
- backend/alembic/versions/xxxx_create_stock_basic.py（新建）
- backend/tests/unit/test_stock_repo.py（新建）

## Definition of Done
- [ ] Alembic upgrade head 干净通过
- [ ] pytest 通过（unit + integration）
- [ ] Ruff + mypy 无告警
- [ ] Repository 提供领域方法（不暴露 ORM Query）
- [ ] Upsert 幂等（重复调用不产生重复行）

## Out-of-scope
- 不做 API 层（下一个任务）
- 不做同步逻辑（P1-05）
- 不改其他表

## 测试提示
- 用 factory-boy 生成 fixture
- 集成测试跑真实 PG（docker-compose 已提供）
- 幂等性用同参数调两次断言行数不变

## 附加说明（可选）
<任何一次性上下文，例如"本任务额外关注 tradestatus 字段的空值语义">
```

---

## 填模板的规范

### Task ID
- 从 `docs/06_TASKS.md` 复制
- 一次会话对应一个 Task ID
- 若发现任务过大（AI 需要拆分），停下来更新 06_TASKS 而非硬做

### 参考文档
- **只列这个任务真正需要的锚点**，不要把整个 05 塞进去
- 锚点用 markdown heading 的最后一级（例如 `#4.3-k_line_daily`）
- 相关 cheatsheet 也列出（`prompt/reference/*.md`）

### 交付物
- **精确列出每个文件的路径与 新建/修改**
- 若涉及跨模块变更（如同时改 model + repo + service），显式列出
- 迁移脚本一律标 `alembic/versions/xxxx_<描述>.py`

### DoD
- 至少覆盖：迁移 / 测试 / lint / 类型 / 幂等（若适用）
- 前端任务额外覆盖：AntD 组件复用 / axios 拦截器复用 / 无 console.error
- API 任务额外覆盖：envelope 合规 / 错误码前缀 / OpenAPI schema 更新

### Out-of-scope
- **必须显式写**，避免 AI 越权重构
- 常见项："不改其他表 / 不加日志基础设施 / 不做前端 / 不写 mock 数据"

### 测试提示
- 单元测试：factory-boy + fake 数据
- 集成测试：真 PG（docker-compose 环境）
- 打通外部 API 的测试：默认打真接口，跑得慢就打 `@pytest.mark.integration`

---

## 示例：一份完整 prompt 组装

```
[粘贴 prompt/CONTEXT.md 全文]

---

# 任务：P1-02 — SQLite + Alembic + 基础表 → 改为 PG + Alembic + 基础表

## Phase
Phase 1 数据基座

## 参考文档（AI 必读）
- docs/05_DATA_MODEL.md#4.1-stock_basic
- docs/05_DATA_MODEL.md#4.2-trade_calendar
- docs/05_DATA_MODEL.md#4.3-k_line_daily
- docs/05_DATA_MODEL.md#6.1-data_update_task
- docs/05_DATA_MODEL.md#10-Alembic迁移策略
- docs/03_MODULES.md#3.3-Repository层

## 关联用户故事
US-2.1、US-2.2、US-2.3

## 交付物
- backend/app/core/db.py（新建）
- backend/app/models/{stock_basic,trade_calendar,k_line_daily,data_update_task}.py（新建）
- backend/app/repositories/{stock_repo,trade_cal_repo,kline_repo,task_log_repo}.py（新建）
- backend/alembic/env.py + versions/0001_initial.py（新建）
- backend/tests/unit/test_repositories.py（新建）

## DoD
- [ ] docker-compose up 后 alembic upgrade head 通过
- [ ] 4 个 Repository 分别支持 upsert（幂等）与基础查询
- [ ] pytest 全绿；ruff / mypy 无告警
- [ ] Repository 只暴露领域方法（不返回 Query 对象）

## Out-of-scope
- 不做 baostock 同步（P1-03）
- 不做健康 API（P1-07）
- 不做前端

## 测试提示
- factory-boy 造 3 支股票 + 5 天 K 线
- 幂等断言：同参数 upsert 两次，行数不变
```

---

## 常见反模式（不要做）

- **粘贴整份 PRD** —— AI 会过度解读，脱离任务范围
- **模糊的 DoD**（"完成功能"）—— 必须可测
- **省略 Out-of-scope** —— AI 会"顺手"改无关模块
- **一个 Task ID 塞多个功能** —— 拆成 P1-02a / P1-02b
- **参考文档只写文件名不写锚点** —— AI 会跳读并遗漏关键条款
