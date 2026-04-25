## 1. Scope and Traceability

- [x] 1.1 按计划确认本次 Change 仅覆盖 MVP 全链路第一阶段，不新增 API/字段
- [x] 1.2 完成 `proposal.md` 并复核四个能力的修改范围（source-governance、hotspot-discovery、digest-delivery、operator-console）

## 2. OpenSpec Artifact Completion

- [x] 2.1 编写 `design.md` 并明确 data flow 与降级策略
- [x] 2.2 补齐 `specs/source-governance/spec.md` 的阶段可验收要求
- [x] 2.3 补齐 `specs/hotspot-discovery/spec.md` 的阶段可验收要求
- [x] 2.4 补齐 `specs/digest-delivery/spec.md` 的阶段可验收要求
- [x] 2.5 补齐 `specs/operator-console/spec.md` 的阶段可验收要求

## 3. Documentation Delivery Alignment

- [x] 3.1 更新 `docs/product/plan.md` 的阶段交付点，新增当前 change 的执行入口与验收映射
- [x] 3.2 更新 `docs/engineering/acceptance.md` 的阶段验收点并指向 PRD 子文件条目
- [x] 3.3 更新 `AGENTS.md`，补充新增字段/API 改动必须同步主链路文档与验收项

## 4. Verification and Closure

- [x] 4.1 运行 `openspec status --change mvp-fullchain-execution-2026-04-25 --json`，确认 artifact 解锁与依赖闭环
- [x] 4.2 运行 `openspec validate mvp-fullchain-execution-2026-04-25`
- [x] 4.3 运行 `openspec validate --specs`
- [x] 4.4 运行文档一致性与链路回归命令（详见 `docs/engineering/acceptance.md` 与现有测试入口）；本地通过文档路径验真与核心单元测试（`test_source_governance`、`test_hotspot_discovery`）；`fastapi` 依赖/`docker` 环境缺失导致 API 与部分链路测试受阻
