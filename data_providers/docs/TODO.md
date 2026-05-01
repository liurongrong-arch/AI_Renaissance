# DataHub TODO（后续工作清单）

本清单按“优先级（P0/P1/P2） + 可拆分任务”整理。

## P0（继续扩展必需）

1. HK/US 财报数据接入
   - 新增 `HKFinancialProvider` / `USFinancialProvider`（或扩展现有 Provider）
   - 统一输出到 `fundamentals.financial_statements.raw`（保持三表 + statement 结构）
   - 复用 `normalize_financial_statements` 或按市场做字段映射

2. 公告 PDF“年报/季报/半年报”精确筛选
   - 目前 CNInfo 采用 searchkey + 本地过滤，容易命中非年报（如半年报）
   - 增加可选参数：`report_type`（annual/semi/quarterly）并在 provider 内做更强过滤

3. 可追溯引用标准化（Citation）
   - 统一一个引用结构：`source` + `pdf_sha256` + `page` + `span`（可选）
   - 在 parsed 输出中增加 `citation` 列（或提供 helper）

## P1（质量与可维护性）

1. symbol 歧义处理策略
   - 当前名称命中多条时取第一条
   - 增加策略开关：`strict=True` 时歧义直接报错并返回候选列表

2. Provider 错误分类与降级
   - 统一 `ProviderError` 的错误码（网络/解析/空数据/限频）
   - 在 Hub 层按错误类型选择重试/切源

3. 缓存落盘治理
   - 增加清理工具（按 TTL 清理 documents/）
   - 支持按 dataset 单独设置 cache_dir（例如 documents 单独目录）

4. 观测与日志
   - 统一日志接口（每次取数记录 dataset/source/耗时/是否命中缓存）
   - 可选打点：失败率、平均耗时、缓存命中率

5. 扩展 DataProvider：Baostock / Tushare
   - 新增 `BaostockProvider`：覆盖 A 股日线（可与 AkShare 对照验证）
   - 新增 `TushareProvider`：覆盖 A 股日线 + 财报/公告等数据（需 Token 管理与限频策略）
   - Provider 输出统一对齐：`price.ohlcv.daily`、`fundamentals.financial_statements.raw`（如可取）
   - 增加 Provider 优先级配置：允许 DataHub 按场景 prefer_sources（例如回测用 Tushare、实时用 AkShare）

## P2（工程化增强）

1. ProviderRegistry
   - 自动发现 providers（避免 DataHub 初始化时手动注入）

2. 并发与批量
   - batch API（多 symbol 多期）
   - 并发下载/解析 PDF（注意限频与缓存）

3. 单元测试
   - schemas/normalizers 的纯函数测试
   - provider 的 contract test（可用录制数据或 mock）
