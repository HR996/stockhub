# baostock 使用 cheatsheet

> 服务端主数据源。文档详情见 https://baostock.com/。
> 本文件只覆盖 istock v1 用得到的接口与坑点。

---

## 生命周期

```python
import baostock as bs

class BaostockSession:
    def __enter__(self):
        rs = bs.login()
        if rs.error_code != '0':
            raise AdapterAuthError(f'baostock login failed: {rs.error_msg}')
        return bs

    def __exit__(self, exc_type, exc, tb):
        bs.logout()
```

- **匿名接入**，无需 token
- **每次任务包裹在 with 块中**，异常也保证 logout
- baostock 内部有 socket，长时间不用会断 —— 每次同步任务重新 login

---

## 关键接口

### 1. 股票列表 —— `query_all_stock`

```python
rs = bs.query_all_stock(day="2026-07-07")
```

- 返回**当日**在市股票（含指数）
- 字段：`code / tradeStatus / code_name`
- 用途：初始化 stock_basic 时对全市场做 code 集合快照

### 2. 股票基本资料 —— `query_stock_basic`

```python
rs = bs.query_stock_basic(code="sh.600000")
# 或全市场
rs = bs.query_stock_basic()
```

- 字段：`code / code_name / ipoDate / outDate / type / status`
- **`type`**：`1=股票 / 2=指数 / 3=其他 / 4=可转债 / 5=ETF`
- **`status`**：`1=上市 / 0=退市`
- **`outDate`**：未退市股票为空字符串（不是 null）
- **是否北交所**：从 `code` 前缀判断（`bj.` 开头）
- **是否普通股票**：`type == '1'`

### 3. 日 K 线 —— `query_history_k_data_plus`

```python
rs = bs.query_history_k_data_plus(
    "sh.600000",
    "date,code,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg,isST",
    start_date="2024-01-01",
    end_date="2026-07-01",
    frequency="d",
    adjustflag="2",   # ← 前复权，因子算法用这个
)
```

**adjustflag 语义（务必记住）**：

| 值 | 含义 | 用途 |
| --- | --- | --- |
| `1` | 后复权 | 存 `*_hfq` 字段 |
| `2` | **前复权** | 存 `*_qfq` 字段，**因子算法用** |
| `3` | 不复权 | 存 `*_raw` 字段 |

**同步 K 线的做法**：同一支股票同一日期区间调 3 次 `query_history_k_data_plus`，分别用 `1/2/3`，然后合并成 `k_line_daily` 一行 3 组字段。

**字段坑**：

- `date` 是字符串 `YYYY-MM-DD`，需转 `date` 类型
- `tradestatus`：`1=交易 / 0=停牌` → 落库到 `trade_status: SMALLINT`
- **停牌日**：仍会返回该日行，但 `open/high/low/close/volume` 为**空字符串**，需过滤或转 null
- `isST`：`1=ST / 0=非ST` → 布尔转换（每行有该值，用于历史 ST 状态判断）
- `preclose`：前收盘（用于对齐算法）

### 4. 交易日历 —— `query_trade_dates`

```python
rs = bs.query_trade_dates(start_date="2024-01-01", end_date="2026-12-31")
```

- 字段：`calendar_date / is_trading_day`
- **`is_trading_day`**：`1=交易日 / 0=非交易日`
- 用途：`trade_calendar` 表全量刷新（v1 每日追加至次年年底）

### 5. 季度财报 / 股本 —— `query_profit_data`（供市值合成）

```python
rs = bs.query_profit_data(code="sh.600000", year=2025, quarter=1)
```

- 字段：`code / pubDate / statDate / roeAvg / npMargin / gpMargin / netProfit / epsTTM / MBRevenue / totalShare / liqaShare`
- **`totalShare` / `liqaShare` 单位是"股"**（不是万股）；乘以收盘价（元/股）得到市值（元）
- 一次调用只返回该 (code, year, quarter) 的 0 或 1 行
- **v1 用途**：合成 `latest_market_cap.total_market_cap = totalShare × close_raw`（详见 `04_TECH_STACK §4.2`）
- **上一季度策略**：为避开新季未披露窗口，`_quarter_of(day)` 取 `day` 所在季度的**上一季度**（Q1 → 上一年 Q4）

**已知覆盖率坑**：
- 沪深主板 / 创业板 / 科创板普通股：完整覆盖
- **部分北交所股票（如 `bj.430047`）无 profit 记录 → 返回 None**；调用方视为 `market_cap_source='baostock_missing'`
- 空 `totalShare` / `liqaShare` 会以空字符串返回，`_parse_decimal` 转 None

---

## 常见异常处理

| 场景 | 处理 |
| --- | --- |
| `error_code != '0'` | 抛 `AdapterDataError(error_msg)` |
| socket 断开 | 抛 `AdapterConnectionError`，Service 层重试 1 次 |
| 部分股票拉不到 K 线（如刚上市） | 记 `data_update_task.missing_count`，不抛异常 |
| 停牌日返回空价格 | 过滤为 `trade_status=0` + 价格 null，不视为异常 |

---

## rs → DataFrame 的模板

```python
def rs_to_df(rs):
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())
    if rs.error_code != '0':
        raise AdapterDataError(f'baostock query failed: {rs.error_msg}')
    return pd.DataFrame(rows, columns=rs.fields)
```

---

## 频率与限流

- **官方限制：单账号 5 万次 / 日**。触顶后 `error_code=10001007 用户请求次数超过限制`，当日不恢复。
- baostock 无 QPS 文档，实测单日全市场 K 线拉取（约 5000 支 × 3 复权）需 30–60 分钟
- 建议同步任务串行执行，避免并发 login
- 同步失败时按股票粒度重试（记 `data_update_task.error_count`）；**重试次数上限 = 1**

## 5 万次 / 日预算分配

生产日常参考（详见 `PROJECT.md §11.5`）：

| 场景 | 次数 |
| --- | --- |
| `sync_stock_basic` 全市场 | 1 / 日 |
| `sync_trade_calendar` | 1 / 日 |
| `sync_kline` 全市场增量（每股 3 复权） | ≈ 15000 / 日 |
| `market_cap` 合成（每股 profit_data） | ≈ 5000 / 日（可降为季度刷） |
| **合计** | **≈ 2 万 / 日**（40%），余 3 万给开发+测试+回补 |

## 开发期反模式（禁止！）

```python
# 反模式 1：按日循环 —— 3 年 × 5000 支 × 3 复权 = 1125 万次，秒杀预算
for day in trading_days:
    fetch_kline(code, day, day, adjustflag)

# 反模式 2：同一 range 重复调用（同一进程内应缓存返回值）
raw1 = fetch_kline(code, start, end, "3")
raw2 = fetch_kline(code, start, end, "3")   # ← 白烧一次

# 反模式 3：单元测试真调
def test_something():
    with baostock_session():                  # ← 单元测试禁网络
        rows = fetch_stock_basic()

# 反模式 4：集成测试反复"跑第二次真接口"验证幂等
def test_idempotent():
    sync_kline_for_stocks(SAMPLE_20, ...)     # 60 次
    sync_kline_for_stocks(SAMPLE_20, ...)     # ← 又 60 次；应用 mock 或已入库数据验证

# 反模式 5：循环内 login/logout
for code in codes:
    with baostock_session():                  # ← 每次登录本身也算 1 次调用
        fetch_kline(code, ...)
```

## 开发期正确姿势

- **一次拉多天**：`fetch_kline(code, start=2024-01-01, end=2026-07-01, adjustflag=...)` 一次搞定
- **fixture 缓存**：把典型返回落到 `tests/fixtures/*.json`，迭代时用 mock，只在打通阶段跑真接口
- **`bs_session` 复用**：所有 integration 测试共用 session-scoped `bs_session` fixture（`tests/conftest.py`），一次 pytest run 只 login 1 次
- **触顶保护**：`_rs_to_df` 检测 `error_code=10001007` 时应立刻抛 `AdapterQuotaExceededError`（若尚未实现，遇到时优先加），Service 捕获后写 FAILED 并停止批量
- **PR 自检**：改 adapter/sync_service 前算清"新增几次真调用"、"单次 pytest 全套约多少次"，写在 PR 描述里

