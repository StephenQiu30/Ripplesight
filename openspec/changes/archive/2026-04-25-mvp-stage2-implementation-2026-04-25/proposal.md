## Why

第一阶段文档闭环完成后，系统在实现面仍存在两处关键断层：运行时未严格使用已启用来源参与发现，和原始信号标准化缺少明确持久化边界。  
这会导致采集治理与追溯链路与阶段2（采集与标准化打通）验收口径不一致，难以直接用于后续 M2~M3 的稳定扩展。

## What Changes

- 在现有源码链路内实现阶段2闭环：采集只消费 `enabled=True` 的来源配置。
- 在 `HotspotDiscoveryService` 中新增“标准化采集+去噪边界”能力，确保归并失败不阻塞主链路。
- 补充 Raw Content 持久化的最小内存存储实现，使每个标准化条目可追溯来源与抓取窗口。
- 在依赖装配层将原始信号与聚类入口统一为“治理后输入”的执行路径。
- 补充阶段2对应的单元测试，覆盖禁用来源过滤、失败源降级、标准化持久化与证据可追溯。

## Capabilities

### New Capabilities

_(当前 change 为现有能力细化，无新能力引入)_

### Modified Capabilities

- `source-governance`: 明确来源启停对发现执行输入的约束，并要求仅允许已启用来源进入聚合流水线。
- `hotspot-discovery`: 明确标准化输出的持久化与来源边界、单源失败隔离执行语义。

## Impact

- 影响代码：
  - `backend/core/application/services.py`
  - `backend/core/application/protocols.py`
  - `backend/core/infrastructure/memory.py`
  - `backend/core/application/__init__.py`
  - `backend/core/infrastructure/__init__.py`
  - `backend/core/domain/__init__.py`
  - `services/api/dependencies.py`
  - `services/worker/bootstrap.py`
- 影响测试：
  - `tests/test_hotspot_discovery.py`
  - `tests/test_api_routes.py`（若执行流程变化，可能需要回归该条目）
- 影响范围：不新增 API、字段或第三方适配器，仅改动内部执行路径与可验证闭环行为。
