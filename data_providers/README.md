# data/ —— 统一数据管理层（方案 + 落地代码）

目标：从“多源信号来源（量价/财报/产业链/地缘/情绪/另类）”中抽象出统一数据接口与返回格式，让 Agent **只管分析**，不关心数据从哪来。

## 设计原则

1. **统一入口**：Agent 只依赖 `DataHub`。
2. **Provider 插件化**：每个数据源一个 Provider（AkShare / 东财 / 自研 / 第三方）。
3. **标准返回格式**：统一返回 `DataResult(df, meta)`。
4. **缓存/限频在 Hub 层**：避免每个 Agent 自己写缓存、写 timeout、被封禁。
5. **最小归一化**：Provider 只做字段口径对齐（如把“日期/开盘/收盘”映射为 `date/open/close`）。

## 关键约定（非常重要）

1. **统一返回 `DataResult`**：
   - `df`：`pandas.DataFrame`
   - `meta`：`dataset/source/fetched_at/cached/params`
2. **时间序列统一 `date` 列**：
   - dtype：`datetime64[ns]`
   - 排序：按 `date` 升序
3. **口径不一致要在 Provider 内解决**：例如 AkShare 的中文列名映射、字段缺失填空、类型转换。

## symbol 输入规范（你刚确认：支持“股票名称/股票代码”）

- Agent/调用方可以传：
- 股票名称：例如 `贵州茅台`
- 股票代码：不同市场格式不同（见下）
- DataHub 会把名称解析成统一代码（`Symbol(code,name,market)`），Provider 侧默认只拿 `code` 拉数。
- 注意：名称可能产生歧义（同名/简称）；当前策略是优先精确匹配，其次包含匹配并取第一条，后续可按你要求改为“歧义即报错”。

### 三市场代码规范（当前已支持：A 股/港股/美股）

- A 股（`market="CN"`）：6 位数字，例如 `600519`
- 港股（`market="HK"`）：4/5 位数字，统一归一化为 5 位（前导 0 补齐），例如 `0700` → `00700`
- 美股（`market="US"`）：
  - 若传“东财美股代码”（AkShare/东财常用形态）：例如 `105.MSFT`，可直接使用
  - 若传常见 ticker（如 `MSFT`/`AAPL`）或名称：会尝试通过 AkShare 的美股 spot 列表映射为东财代码（映射失败会报错）

## 数据集目录（当前已落地）

- `price.ohlcv.daily`：量价日线（OHLCV，当前阶段只做日线）
- `price.spot.quote`：A 股实时行情（spot）

## 财报数据（你确认：raw + normalized 都要，可选产出）

已落地两套数据集：

- `fundamentals.financial_statements.raw`：三表 raw（宽表 + `statement` 标记）
- `fundamentals.financial_statements.normalized`：七步验证链常用指标集（宽表，一行一个报告期）

### 市场支持

- 当前 raw/normalized 先支持 `market="CN"`（数据源：东方财富 NewFinanceAnalysis）
- HK/US 的财报数据将按同一套数据集扩展（Provider 侧补齐即可）

### raw 输出约定（`fundamentals.financial_statements.raw`）

- `df` 至少包含：
  - `statement`：`balance|income|cashflow`
  - 其余列：保持数据源原字段（例如东财的 `PARENT_NETPROFIT`、`NETCASH_OPERATE` 等）

### normalized 输出约定（`fundamentals.financial_statements.normalized`）

`df` 目前输出字段（与七步验证链直接相关）：
- `report_date`
- 利润表：`revenue/net_profit/operating_profit/financial_expense`
- 现金流量表：`operating_cf/sales_cash/capex`
- 资产负债表：`accounts_receivable/inventory/contract_liability/construction_in_progress/fixed_assets/cash/short_borrowing/long_borrowing/equity`

后续扩展建议（同一套路）：
- `fundamentals.financial.statements`：三表/财报指标（东财 JSON、AkShare、Wind/聚宽等）
- `documents.announcements.pdf`：公告 PDF（巨潮等）下载/解析/溯源
- `macro.*`：宏观
- `sentiment.*`：新闻/社媒情绪

## 目录结构

```
data/
├── README.md                 # 设计说明（本文件）
├── __init__.py
├── hub.py                    # DataHub：路由/缓存/限频/兜底
├── schemas.py                # DatasetType + Request/Result/Meta
├── errors.py                 # 统一异常
├── cache.py                  # 极简磁盘缓存
├── rate_limit.py             # 限频器
└── providers/
    ├── base.py               # Provider 抽象
    └── akshare_provider.py   # AkShare 示例（量价日线 + 实时行情）
```

## 统一接口（Agent 侧怎么用）

### 1) 取 A 股日线（OHLCV）

```python
from data_providers import DataHub, PriceOHLCVRequest

hub = DataHub()
res = hub.get_price_ohlcv_daily(
    # symbol 支持“代码/名称”
    PriceOHLCVRequest(symbol="贵州茅台", market="CN", start_date="2024-01-01", end_date="2024-12-31", adjust="qfq")
)
df = res.df
```

约定列（尽可能提供）：`date/open/high/low/close/volume/amount/pct_change/change/turnover`

### 2) 取实时行情（spot）

```python
from data_providers import DataHub, SpotQuoteRequest

hub = DataHub()
res = hub.get_spot_quote(SpotQuoteRequest(symbol="贵州茅台", market="CN"))
quote_df = res.df
```

### 3) 港股示例（HK）

```python
from data_providers import DataHub, PriceOHLCVRequest

hub = DataHub()
res = hub.get_price_ohlcv_daily(PriceOHLCVRequest(symbol="0700", market="HK"))  # 自动补齐为 00700
df = res.df
```

### 4) 美股示例（US）

```python
from data_providers import DataHub, PriceOHLCVRequest

hub = DataHub()
# 推荐：直接传东财美股代码（例如 105.MSFT）
res = hub.get_price_ohlcv_daily(PriceOHLCVRequest(symbol="105.MSFT", market="US"))
df = res.df
```

### 5) 财报 raw / normalized 示例（CN）

```python
from data_providers import DataHub, FinancialStatementsRequest

hub = DataHub()

# raw：三表宽表（含 statement 列）
raw = hub.get_financial_statements_raw(FinancialStatementsRequest(symbol="贵州茅台", market="CN"))
raw_df = raw.df

# normalized：七步验证链常用指标集（可选产出）
norm = hub.get_financial_statements_normalized(FinancialStatementsRequest(symbol="贵州茅台", market="CN"))
norm_df = norm.df
```

## 公告 PDF（你确认：第一期必须做“巨潮 PDF 原文 + 可追溯引用”）

已落地两套数据集：
- `documents.announcements.pdf.raw`：下载 PDF 原文并落盘（返回 `pdf_path/pdf_sha256` 等元数据）
- `documents.announcements.pdf.parsed`：逐页解析文本（返回 page 级表，引用时按 `page` 标注即可）

市场支持：
- 当前仅支持 `market="CN"`（CNInfo 巨潮）

### 6) 下载公告 PDF（raw）

```python
from data_providers import DataHub, AnnouncementPDFRequest

hub = DataHub()
raw = hub.get_announcement_pdf_raw(
    AnnouncementPDFRequest(
        symbol="贵州茅台",
        market="CN",
        keyword="年报",
        start_date="2023-01-01",
        end_date="2024-12-31",
    )
)
meta_df = raw.df  # 包含 pdf_path/pdf_sha256/title/published_at 等
```

### 7) 解析公告 PDF（parsed，可追溯引用）

```python
from data_providers import DataHub, AnnouncementPDFRequest

hub = DataHub()
parsed = hub.get_announcement_pdf_parsed(
    AnnouncementPDFRequest(symbol="600519", market="CN", keyword="年报")
)
pages = parsed.df  # 列：pdf_path/pdf_sha256/page/text/char_count

# 引用示例：取第 3 页
page3 = pages[pages["page"] == 3]["text"].iloc[0]
```

## 如何扩展新数据源（Provider）

1. 在 `data/providers/` 新增一个 Provider（例如 `eastmoney_provider.py`）
2. 实现 `capabilities` 与对应方法（如 `get_price_ohlcv_daily`）
3. 在 `DataHub(providers=[...])` 中注册，或后续做统一的 ProviderRegistry

## 缓存与限频

- 缓存：`data/cache.py` 使用 pickle 存储 `DataFrame`，默认落在 `~/.cache/ai_renaissance/datahub/`
- 限频：`data/rate_limit.py` 采用“同一 Provider+Dataset 最小间隔”策略（默认 0.2s）

### 分级缓存策略（你确认：分级）

DataHub 默认按 dataset 分级 TTL（可在 `DataHub(cache_ttls=...)` 覆盖）：
- `price.ohlcv.daily`：24h
- `fundamentals.financial_statements.raw`：7d
- `fundamentals.financial_statements.normalized`：7d
- `documents.announcements.pdf.raw`：30d（同时 PDF 会落盘到 `~/.cache/ai_renaissance/datahub/documents/`）
- `documents.announcements.pdf.parsed`：30d

覆盖示例：
```python
from data_providers import DataHub, DatasetType

hub = DataHub(cache_ttls={
    DatasetType.PRICE_OHLCV_DAILY: 6 * 3600,
    "documents.announcements.pdf.parsed": 90 * 24 * 3600,
})
```

## 下一步建议（待你确认口径）

为了覆盖“全域信息”，建议把数据集扩展为：
- `fundamentals.financial.statements`（三表/财报指标）
- `documents.announcements.pdf`（巨潮/公告 PDF 下载与解析）
- `macro.*`（利率/汇率/PMI）
- `sentiment.*`（新闻/社媒情绪）

这些都可以复用同一套：`DatasetType + Request + DataResult + Provider`。
