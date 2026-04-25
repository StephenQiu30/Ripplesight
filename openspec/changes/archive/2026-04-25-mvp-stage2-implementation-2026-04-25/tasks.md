## 1. 需求与规格对齐

- [x] 1.1 完成 proposal/design/specs 文档，确认变更只覆盖阶段2执行边界

## 2. 核心实现

- [x] 2.1 添加 `RawContentItemRepository` 协议与内存实现，并导出到 `backend/core/{application,infrastructure}/__init__.py`
- [x] 2.2 在 `HotspotDiscoveryService` 增加基于 `enabled` 的来源过滤与失败容忍的标准化采集路径
- [x] 2.3 在 API 与 worker 装配层使用统一的标准化入口，并保持现有路由/任务返回结构不变

## 3. 回归与验收

- [x] 3.1 补充阶段2单测（禁用来源过滤、失败源降级、标准化持久化/来源追溯）
- [x] 3.2 运行 `openspec status --change mvp-stage2-implementation-2026-04-25 --json`
- [x] 3.3 运行 `openspec validate mvp-stage2-implementation-2026-04-25` 与 `openspec validate --all --no-interactive`
- [x] 3.4 运行阶段2相关测试链路（`tests.test_source_governance`、`tests.test_hotspot_discovery`、`tests.test_digest_search_feedback_api`）
