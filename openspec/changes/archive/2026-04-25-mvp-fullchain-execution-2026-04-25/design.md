## Context

当前仓库已具备 PRD 分拆、执行计划、技术方案、OpenAPI 与基础读写链路。为避免再次陷入“先做代码再补文档”的返工，当前 change 聚焦于 OpenSpec 第一阶段“闭环交付定义”。

本次范围固定在 MVP 全链路可验证能力内，不新增新平台接入，也不改变 OpenAPI 主体实体。我们只要求：
- 来源治理约束明确；
- 多源聚合与评分有可追溯规则；
- 日报产出与邮件送达可闭环记录；
- 控制台基础展示链路可被验证；
- 这些能力通过 `plan.md` 与 `acceptance.md` 的阶段交付点可追溯。

## Goals / Non-Goals

**Goals:**
- 形成可执行的 MVP 第一阶段 OpenSpec 能力闭环（仅涉及基础读链路）。
- 在 `source-governance`、`hotspot-discovery`、`digest-delivery`、`operator-console` 四个能力中明确 P0 交付条件和验收场景。
- 对齐文档导航和验收入口，保证实现前后“该改什么、为谁验收”一致。

**Non-Goals:**
- 新增平台、扩展采集能力、增加实时告警、补齐生产级监控告警体系。
- 调整 OpenAPI 实体模型或新增字段/接口（除非已有计划内变更同步更新后再执行）。
- 重新制定长期评分公式与细粒度运营策略，这部分留在后续迭代中补充。

## Decisions

### Decision: 以“四能力+阶段交付点”驱动 MVP 全链路闭环

采用既有能力名（`source-governance`、`hotspot-discovery`、`digest-delivery`、`operator-console`）作为变更范围，不新增能力名，确保与先前 `openspec/specs` 基线一致、便于后续增量合并。

Alternatives considered:
- 新增一个“fullchain-execution”大能力：拒绝，因为会掩盖边界。
- 把文档修改拆散到多个无关 change：拒绝，增加追踪成本。

### Decision: 保持“无新 API/字段”约束，聚焦验收闭环

本轮不新增端点或实体，以避免越界导致 openapi 与实现漂移，先用现有契约做链路闭环验证。

Alternatives considered:
- 新增 API 快速修复验收缺口：拒绝，当前目标是文档与执行闭环一致性，不是快速堆功能。

### Decision: 文档即驱动：每个阶段交付点都绑定 PRD 子文件

将 `docs/product/plan.md` 与 `docs/engineering/acceptance.md` 的阶段验收条目改为可追溯到 `prd/01-...`~`prd/05`，避免“同名需求散落”.

Alternatives considered:
- 保持现状不做交付点映射：拒绝，当前已导致实现与验收口径对齐成本高。

## Data Flow Boundary and Degradation Strategy

- **输入边界**：优先级仅覆盖已批准来源与 X 官方 API 路径；不把采集脚本抓取纳入主链路。
- **处理边界**：`source-governance → hotspot-discovery → digest-delivery → operator-console` 按顺序，任何阶段仅输出本阶段可消费的中间模型。
- **降级策略**：任一上游源失败时，当前阶段应继续处理剩余可用信号，避免全链路中断；仅在缺失关键证据导致不能形成可核实事件时降级为“事件质量异常”状态并记录。
- **交付边界**：邮件发送作为 MVP 唯一外部交付渠道，控制台为只读查询入口，不承担写型状态变更（反馈除外）。

## Risks / Trade-offs

- [范围再扩大风险] → 只允许修改现有能力，且 tasks 与 proposal 明确列出不可做事项。
- [文档-验收脱节风险] → 以 Plan/Acceptance 的阶段交付项替代口头约定。
- [X 信号噪声风险] → 保持评分中跨源权重约束，不允许 X 信号单独决定榜单。
- [验收过重或过轻风险] → 所有场景转为可执行测试目标，不要求未实现功能的主观评估。

## Migration Plan

1. 用本 change 的 Proposal 解锁 Design 和 Specs。
2. 在 4 个能力的 spec 文件中补齐第一阶段可追溯要求与场景。
3. 更新 `docs/product/plan.md` 与 `docs/engineering/acceptance.md` 的阶段交付映射。
4. 更新 `AGENTS.md` 的变更同步约束。
5. 逐条执行并打勾 `tasks.md`，完成后进行 `openspec validate` 及关键回归命令。

## Open Questions

- 是否在本阶段显式引入邮件失败重试次数上限（当前保持现状，作为后续优化项）?
- 对控制台反馈（收藏/忽略/误报）是否在 MVP 首轮作为读写闭环外功能暂不进入？
