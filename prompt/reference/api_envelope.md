# API envelope 详细约定

> 补充 `docs/04_TECH_STACK.md §7`。所有后端 API 无一例外遵守。

---

## 响应 envelope

```json
{
  "success": true,
  "data": <any>,
  "message": ""
}
```

- **HTTP 状态码只标识传输层**（200 / 4xx / 5xx）
- **`success` 标识业务是否成功**：业务错误也可返回 200 + `success=false`
- **`data`**：任意 JSON 对象或数组；不返回 `null` 除非语义确实是"无"
- **`message`**：失败时的用户可读文案；成功时空串

**为什么用 envelope 而不是 REST 惯例状态码？**

- 前端拦截器统一处理更简单（一处判断 `success`）
- 用户可读的 message 与 machine-readable 的 code 分离
- HTTP 中间件（nginx / 网关）不干扰业务错误

---

## 失败响应结构

```json
{
  "success": false,
  "data": {
    "code": "VALIDATION_INVALID_DATE",
    "detail": {
      "field": "basedate",
      "reason": "not a trading day"
    }
  },
  "message": "计算日期必须为交易日"
}
```

- `data.code`：错误码（前缀分类见下）
- `data.detail`：可选，供 debug 或前端表单联动
- `message`：用户可读

---

## 错误码前缀

| 前缀 | 场景 |
| --- | --- |
| `AUTH_*` | 未登录 / 用户名不存在 / 密码错误 |
| `VALIDATION_*` | 参数校验失败（表单类） |
| `NOT_FOUND_*` | 资源不存在 |
| `CONFLICT_*` | 冲突（重复用户名 / 重名配置） |
| `ADAPTER_*` | 外部数据源错误（baostock / akshare） |
| `PARSER_*` | 申万解析失败 |
| `INTERNAL_*` | 未分类内部错误（前端展示"服务异常"） |

**约定**：错误码全大写下划线；分类前缀 + 具体标识（如 `AUTH_USER_NOT_FOUND`）。

---

## 分页

**请求**（GET query 或 POST body）：

```
?page=1&page_size=50
```

- `page` 从 1 开始
- `page_size` 上限 200，默认 50
- 超过上限返回 `VALIDATION_PAGE_SIZE_TOO_LARGE`

**响应 `data` 结构**：

```json
{
  "items": [ ... ],
  "total": 12345,
  "page": 1,
  "page_size": 50
}
```

---

## 排序

单字段：`?order_by=trade_date&order=desc`

多字段：`?order_by=trade_date,ts_code&order=desc,asc`

- 允许排序的字段由后端 whitelist（防 SQL 注入 / 乱查）
- whitelist 违反返回 `VALIDATION_INVALID_ORDER_FIELD`

---

## 筛选（POST body）

复杂筛选走 POST，`filters` 为对象数组：

```json
{
  "filters": [
    { "field": "ts_code", "op": "in", "value": ["600000.SH", "000001.SZ"] },
    { "field": "trade_date", "op": "ge", "value": "2026-01-01" },
    { "field": "trade_status", "op": "eq", "value": 1 }
  ]
}
```

**支持的 `op`**：

| op | 语义 |
| --- | --- |
| `eq` | 等于 |
| `ne` | 不等于 |
| `in` | value 是数组 |
| `nin` | not in |
| `gt` / `ge` | 大于 / 大于等于 |
| `lt` / `le` | 小于 / 小于等于 |
| `like` | 模糊（前后加 `%`） |
| `is_null` | value 忽略 |
| `not_null` | value 忽略 |

**约束**：

- filter 字段也需 whitelist
- 非 whitelist 字段返回 `VALIDATION_INVALID_FILTER_FIELD`
- `like` 操作需转义 `%` `_`

---

## 时间格式

- **带时刻**：ISO 8601 + 时区（`2026-07-07T13:45:00+08:00`）
- **纯日期**：`YYYY-MM-DD`
- **应用层内部存 UTC**，出入 API 时前端展示 `Asia/Shanghai`

---

## Header 约定

| Header | 说明 | 出现位置 |
| --- | --- | --- |
| `X-User` | 当前用户名 | 所有请求 |
| `X-Admin-Password` | sha256(明文) | 敏感操作请求 |
| `X-Request-Id` | UUID | 前端注入，后端记入 audit_log（可选） |
| `Content-Type` | `application/json` | POST/PUT |

---

## FastAPI 实现模板

```python
from fastapi import APIRouter, Depends
from app.core.envelope import ok, fail
from app.core.deps import get_current_user

router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("/summary")
def health_summary(user: str = Depends(get_current_user)):
    data = health_service.get_summary()
    return ok(data)
```

`ok` / `fail` 定义在 `app/core/envelope.py`：

```python
def ok(data: Any = None, message: str = "") -> dict:
    return {"success": True, "data": data or {}, "message": message}

def fail(code: str, message: str, detail: dict | None = None) -> dict:
    return {
        "success": False,
        "data": {"code": code, "detail": detail or {}},
        "message": message,
    }
```

---

## 前端 axios 拦截器模板

```typescript
axios.interceptors.request.use((config) => {
  config.headers['X-User'] = getStoredUser();
  return config;
});

axios.interceptors.response.use(
  (res) => {
    if (!res.data.success) {
      throw new EnvelopeError(res.data.data?.code, res.data.message);
    }
    return res.data.data;   // 直接解包 data
  },
  (err) => {
    // HTTP 层错误
    throw new NetworkError(err);
  },
);
```
