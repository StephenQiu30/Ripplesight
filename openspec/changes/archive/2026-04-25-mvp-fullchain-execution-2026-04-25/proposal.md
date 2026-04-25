## Why

MVP 目标已明确为“监听 → 聚合 → 评分 → 日报 → 邮件 → 控制台基础读链路”，但当前仓库在执行与验收口径上还未形成一次可直接驱动闭环交付的 OpenSpec 全链路文件。
这个 change 的目的，是在不扩展新功能边界的前提下，把第一阶段可落地范围和执行验收定义清晰化，并绑定到已拆分 PRD 子文件和既有实现入口。

## What Changes

- 将 PRD 一阶段目标转化为 OpenSpec 变更约束，限定本次只覆盖 MVP 全链路闭环的第一阶段能力。
- 为 `source-governance`、`hotspot-discovery`、`digest-delivery`、`operator-console` 四个既有能力补齐可验证的需求条目与场景。
- 同步更新 `docs/product/plan.md` 与 `docs/engineering/acceptance.md` 的阶段交付点，明确指向 PRD 子文档条目。
- 明确 AGENTS 约束：新增字段或 API 时必须同步更新主链路文档和验收项。
- 不新增平台功能，不新增 API，不改变当前 OpenAPI/技术方案的实体形态，只做交付口径与验收闭环的收紧。

## Capabilities

### New Capabilities

- 暂无

### Modified Capabilities

- `source-governance`: 明确 MVP 第一阶段来源治理与来源边界行为（含 X 官方 API 使用边界）。
- `hotspot-discovery`: 明确第一阶段的标准化、聚类、去重、评分和证据保留行为，并约束降级策略。
- `digest-delivery`: 明确每天一次、中文日报、邮件投递与投递状态记录的可验收行为。
- `operator-console`: 明确控制台基础读链路（列表、详情、来源追踪、搜索与反馈）的最小闭环。

## Impact

- `openspec/changes/mvp-fullchain-execution-2026-04-25/`: 新增变更级 `proposal.md`、`design.md`、`specs/**/spec.md` 和 `tasks.md`。
- `docs/product/plan.md`: 新增/更新 OpenSpec 阶段交付与验收映射。
- `docs/engineering/acceptance.md`: 新增 OpenSpec 第一阶段可追溯验收点。
- `AGENTS.md`: 补充“新增字段/API 改动同步主链路文档与验收”的执行约束。
