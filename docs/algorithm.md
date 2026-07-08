# 市场板块动量因子最终算法

## 1. 核心思想

市场板块动量因子用于识别 A 股市场中具备集体上涨特征的强势行业板块。

算法先在全市场范围内找出强势股票集合，再按行业板块聚合，计算板块强度。

v1 同时提供两种评分方法：

```text
方法一：median_return_score
momentum_score = top_density × median_return
```

```text
方法二：top_count_score
momentum_score = top_density × sector_top_stock_count
```

---

## 2. 两种评分方法的含义

### 2.1 方法一：median_return_score

```text
momentum_score = top_density × median_return
```

含义：

```text
同时考察板块上涨广度和板块整体收益深度。
```

适合识别：

```text
板块内多数股票表现较好，且整体收益水平较高的强势板块。
```

---

### 2.2 方法二：top_count_score

```text
momentum_score = top_density × sector_top_stock_count
```

因为：

```text
top_density = sector_top_stock_count / sector_stock_count
```

所以该方法等价于：

```text
momentum_score = sector_top_stock_count² / sector_stock_count
```

含义：

```text
更强调板块内进入全市场 Top 集合的股票数量。
```

适合识别：

```text
强势股票集中出现的热门板块。
```

注意：

```text
该方法对大板块更友好，因为大板块更容易拥有更多 Top 股票。
```

---

## 3. 参数

| 参数               | 含义           | 默认值                   |
| ---------------- | ------------ | --------------------- |
| `basedate`       | 基准日，必须是有效交易日 | 用户指定                  |
| `window`         | 动量窗口，交易日数    | `20`                  |
| `top_ratio`      | 全市场 Top 股票比例 | `0.15`                |
| `classification` | 行业分类体系       | `SW`                  |
| `level`          | 行业层级         | `L2`                  |
| `return_method`  | 收益方式         | `simple`              |
| `score_method`   | 评分方法         | `median_return_score` |

`return_method` 只支持：

```text
simple
log
```

`score_method` 支持：

```text
median_return_score
top_count_score
```

---

## 4. 过滤规则

先从全市场股票中筛出 `valid_stocks`。

| 规则    | 条件                           | 判定时点         |
| ----- | ---------------------------- | ------------ |
| 剔除 ST | 名称不含 `ST`、`*ST`、`SST`        | `start_date` |
| 剔除北交所 | 非北交所股票                       | 静态属性         |
| 市值门槛  | 最新总市值 >= 100 亿元              | 最新可得数据       |
| 上市天数  | 截至 `start_date` 上市交易日数 >= 20 | `start_date` |
| 名称过滤  | 名称不含“指数”等衍生标识                | 最新名称         |

---

## 5. 日期规则

```text
start_date = basedate 向前回溯 window 个交易日
```

约束：

1. `basedate` 必须是交易日；
2. 非交易日直接拒绝；
3. `start_date` 必须按交易日历回溯；
4. 不按自然日回溯。

---

## 6. 个股收益

使用前复权收盘价：

```text
price_start = adj_close(stock, start_date)
price_end = adj_close(stock, basedate)
```

### simple

```text
stock_return = price_end / price_start - 1
```

### log

```text
stock_return = ln(price_end / price_start)
```

若缺少 `start_date` 或 `basedate` 的前复权收盘价，该股票不参与计算，并记录缺失原因。

---

## 7. 全市场 Top 股票集合

对所有成功计算收益的股票按 `stock_return` 降序排序：

```text
top_count = ceil(top_ratio × valid_return_stock_count)
```

取前 `top_count` 只股票：

```text
top_stocks = 全市场收益排名前 top_count 的股票
```

关键约束：

1. `top_stocks` 在全市场范围内计算；
2. `top_stocks` 与行业分类无关；
3. 不同分类体系共用同一批个股收益结果。

---

## 8. 板块聚合

按用户选择的：

```text
classification
level
```

将股票映射到行业板块。

每个板块计算：

```text
sector_stock_count = 板块内成功计算收益的股票数
```

```text
sector_top_stock_count = 板块内属于 top_stocks 的股票数
```

```text
top_density = sector_top_stock_count / sector_stock_count
```

```text
median_return = 板块内 stock_return 的中位数
```

---

## 9. 板块评分

### 9.1 median_return_score

```text
momentum_score = top_density × median_return
```

特点：

1. 同时考虑强势股票占比和板块整体收益；
2. 对单票暴涨不敏感；
3. 更偏“集体上涨质量”；
4. 推荐作为默认评分方法。

---

### 9.2 top_count_score

```text
momentum_score = top_density × sector_top_stock_count
```

等价于：

```text
momentum_score = sector_top_stock_count² / sector_stock_count
```

特点：

1. 强调板块内 Top 股票数量；
2. 更偏“热门股票聚集度”；
3. 对大板块更友好；
4. 不直接使用行业中位收益，但仍依赖个股收益排名生成 `top_stocks`。

---

## 10. 小样本规则

默认：

```text
sector_stock_count < 5
```

则：

```text
small_sample_flag = true
```

小样本板块不强制剔除，但必须在结果中提示。

---

## 11. 输出字段

| 字段                       | 含义         |
| ------------------------ | ---------- |
| `basedate`               | 基准日        |
| `start_date`             | 起始交易日      |
| `window`                 | 动量窗口       |
| `top_ratio`              | Top 比例     |
| `classification`         | 行业分类体系     |
| `level`                  | 行业层级       |
| `return_method`          | 收益方式       |
| `score_method`           | 评分方法       |
| `sector_code`            | 板块代码       |
| `sector_name`            | 板块名称       |
| `sector_stock_count`     | 板块有效股票数    |
| `sector_top_stock_count` | 板块 Top 股票数 |
| `top_density`            | 上榜密度       |
| `median_return`          | 行业中位收益     |
| `momentum_score`         | 板块动量得分     |
| `small_sample_flag`      | 是否小样本      |
| `created_at`             | 计算时间       |
| `created_by`             | 计算用户       |

---

## 12. 伪代码（多层级并行版）

```text
function calculate_sector_momentum(config):

    basedate = config.basedate
    window = config.window
    top_ratio = config.top_ratio
    return_method = config.return_method
    score_method = config.score_method
    classification = config.classification
    default_level = config.level  # 仅决定前端"默认展示层级"，不限制计算范围

    if basedate is not trading day:
        reject

    start_date = get_previous_trading_day(basedate, window)

    all_stocks = load_all_stocks()

    valid_stocks = filter all_stocks by:
        - not ST at start_date
        - not BJ
        - latest_market_cap >= 10000000000
        - listed trading days until start_date >= 20
        - name does not contain "指数"

    stock_returns = []

    for stock in valid_stocks:
        price_start = get_adj_close(stock, start_date)
        price_end = get_adj_close(stock, basedate)

        if price_start or price_end is missing:
            record missing quote (missing_reason)
            continue

        if return_method == "simple":
            stock_return = price_end / price_start - 1
        if return_method == "log":
            stock_return = ln(price_end / price_start)

        stock_returns.add(stock, stock_return)

    sort stock_returns by stock_return desc
    top_count = ceil(top_ratio * count(stock_returns))
    top_stocks = first top_count stocks

    # ------ 关键：一次计算跨全部层级 ------
    levels = levels_of(classification)     # SW: [L1, L2, L3]；CSRC: [L1]

    all_sector_results = []
    for level in levels:
        sector_map_at_level = load_sector_mapping(classification, level)
        # 同一批 stock_returns / top_stocks 分别按 L1 / L2 / L3 分组
        grouped = group stock_returns by sector_map_at_level

        for sector in grouped:
            sector_stock_count = count(sector.stocks)
            sector_top_stock_count = count(stocks in sector that are in top_stocks)

            top_density = sector_top_stock_count / sector_stock_count
            median_return = median(stock_return of sector.stocks)

            if score_method == "median_return_score":
                momentum_score = top_density * median_return
            if score_method == "top_count_score":
                momentum_score = top_density * sector_top_stock_count

            small_sample_flag = sector_stock_count < 5

            all_sector_results.add({
                level: level,
                sector_code, sector_name,
                parent_sector_code: parent_of(sector, classification, level),
                sector_stock_count, sector_top_stock_count,
                top_density, median_return,
                momentum_score, small_sample_flag,
            })

    # ------ 落库：跨层级共享同一个 factor_result 头 ------
    persist factor_result(params, industry_version_id, ...)
    persist factor_result_row * len(all_sector_results)   # 每行含 level + parent_sector_code
    persist factor_result_stock * len(stock_returns)      # 个股收益快照，含 l1_code / l2_code / l3_code + is_top

    return { default_level_result: filter(all_sector_results, level=default_level) }
```

**关键点**：

- `stock_returns` 与 `top_stocks` 只算一次，全部层级共用（保证不同层级的 Top 集合完全一致）
- 各层级的 `sector_map` 独立加载，产出各自的板块聚合
- 每个 `factor_result_row` 携带 `level`（`L1`/`L2`/`L3`）与 `parent_sector_code`，支撑下钻查询
- `factor_result_stock` 单独存放个股收益快照，供板块股票列表按收益率降序展示（US-7.5）

---

## 13. 推荐默认配置

```yaml
factor:
  name: market_sector_momentum
  window: 20
  top_ratio: 0.15
  return_method: simple
  score_method: median_return_score

classification:
  system: SW
  level: L2       # 默认展示层级，不影响计算范围（L1/L2/L3 一次全算）

filter:
  exclude_st: true
  exclude_bj: true
  min_market_cap: 10000000000
  min_listed_days: 20
  exclude_index_name: true

warning:
  min_sector_stock_count: 5
```
