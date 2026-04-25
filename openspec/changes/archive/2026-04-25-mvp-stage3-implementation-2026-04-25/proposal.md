## Why

阶段 2 已经把来源信号采集到 `RawContentItem` 层，但热点事件仍主要靠“同标题完全一致”聚合，这会导致跨源同一事件错分片，X 噪声更容易跑进榜单前列。  
本轮变更的目标是先做 MVP 级别的事件发现质量闭环：在不改 API 和外部依赖的前提下，提升热点事件聚类与评分稳定性，让后续日报和控制台可按“跨源可信度”排序。

## What Changes

- 强化 `hotspot-discovery` 的去重与聚类策略：支持同一事件标题轻微差异版本的同源匹配，避免重复事件。  
- 强化评分规则：保留 `X` 信号优势的同时，确保单点 X 信号不会压过跨源协同证据。  
- 补齐阶段 3 的实现验收测试，并将验收里程碑从文档状态同步到 `plan.md` / `acceptance.md`。  

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `hotspot-discovery`: 调整事件聚类与评分能力，新增可验证的“近似标题聚类”与“跨源降噪”行为定义。

## Impact

- 影响代码：`backend/core/domain/hotspot_rules.py`（聚类与评分规则）、`tests/test_hotspot_discovery.py`（新增阶段验收场景）。  
- 影响文档：`docs/product/plan.md` 与 `docs/engineering/acceptance.md` 阶段 3 里程碑状态。  
- 不涉及 API 契约变更、不新增来源接入、不新增数据库 schema。
