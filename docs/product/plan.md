# AI 热点平台执行计划

## 1. 计划概述

本项目按“文档定标 -> 数据链路打通 -> 事件能力成型 -> 日报与控制台闭环”的顺序推进。目标不是一次做全，而是在保证规范的前提下，逐步完成可交付的 MVP。

## 2. 总体阶段

### 阶段 1：文档与契约冻结

- 目标：
  - 冻结产品范围、技术选型、数据来源边界和验收标准
- 输入：
  - 综合需求分析母稿
  - 已确认的产品和技术决策
- 输出：
  - PRD
  - Plan
  - Market Research
  - Tech Spec
  - Acceptance
  - OpenAPI 契约基线
- 完成标准：
  - 文档职责清晰
  - 产品、研发、项目负责人对范围和边界理解一致
- 主要风险：
  - 继续把新增内容写回单一综合文档，导致事实源混乱

### 阶段 2：采集与标准化打通

- 目标：
  - 建立多源采集与统一标准化链路
- 输入：
  - 已冻结的来源边界
  - 已确认的数据模型
- 输出：
  - 各来源采集能力
  - 统一 `RawContentItem` 数据结构
  - 来源配置模型
- 完成标准：
  - 主要来源均能落成统一结构
  - 来源可以单独启停与配置
- 主要风险：
  - 来源数据差异大，标准化不一致

### 阶段 3：事件发现与评分

- 目标：
  - 形成热点事件模型与排序能力
- 输入：
  - 标准化后的原始内容
- 输出：
  - 去重规则
  - 聚类规则
  - 热度评分规则
  - X 降噪规则
- 完成标准：
  - 同一事件可被跨源聚合
  - 噪声不轻易进入榜单前列
- 主要风险：
  - 聚类和评分效果不稳定

### 阶段 4：日报生成与邮件闭环

- 目标：
  - 让事件结果转化为可读的日报交付
- 输入：
  - 热点事件列表
  - 摘要与证据链
- 输出：
  - 中文日报
  - 邮件模板
  - 发送与投递状态记录
- 完成标准：
  - 每日可稳定产出一份结构完整的热点日报
  - 每条事件带来源链接
- 主要风险：
  - 摘要质量不稳定
  - 邮件送达链路不稳

### 阶段 5：控制台与搜索闭环

- 目标：
  - 提供网页端浏览和检索能力
- 输入：
  - 热点事件数据
  - 日报数据
  - 来源追踪数据
- 输出：
  - 今日热点页
  - 热点详情页
  - 搜索与筛选页
- 完成标准：
  - 用户可查看热点榜、详情、来源链路与搜索结果
- 主要风险：
  - 前后端契约不一致

## 3. 推荐推进顺序

1. 冻结文档体系和契约
2. 打通最有代表性的来源链路
3. 完成标准化、去重与聚类
4. 补上 X 专项链路
5. 生成日报并完成邮件投递
6. 最后完善控制台体验

## 4. 资源与协作假设

- 产品和研发按同一套文档协作
- 当前阶段优先完成决策与设计，不扩展未确认范围
- 技术路线已定，不再反复更换主栈

## 5. 里程碑判定

- M1：文档体系完成，产品范围与技术边界冻结
- M2：采集与标准化可用
- M3：事件聚类与评分可用
- M4：日报生成与邮件闭环可用
- M5：控制台浏览与搜索可用

## 6. OpenSpec 执行计划（MVP 全链路）

### 6.1 执行入口

- 对应 OpenSpec 变更：`mvp-fullchain-execution-2026-04-25`
- 本轮目标：按 MVP 第一阶段闭环补齐能力定义与验收映射（监听/聚合/评分/日报/邮件/控制台基础读链路）。
- 主事实源文档：
  - `docs/product/prd.md`（入口）
  - `docs/product/prd/01-goals-and-positioning.md`
  - `docs/product/prd/02-scope-and-non-scope.md`
  - `docs/product/prd/03-features-by-phase-p0-p1.md`
  - `docs/product/prd/04-success-metrics.md`
  - `docs/product/prd/05-risks-and-assumptions.md`
  - `docs/product/plan.md`
  - `docs/research/market-research.md`
  - `docs/engineering/tech-spec.md`
  - `docs/engineering/acceptance.md`
  - `contracts/openapi/openapi.yaml`
- `docs/requirements-analysis.md` 仅作为归档导航入口，不再直接作为规格沉淀来源

### 6.2 能力交付映射（第一阶段）

- `source-governance`：
  - [x] 范围边界与来源治理来源于 [02-范围与非目标](./prd/02-scope-and-non-scope.md)。
  - [x] 与 X 接入约束来自 [02-范围与非目标](./prd/02-scope-and-non-scope.md) 与 [Tech Spec X 实现章节](../engineering/tech-spec.md#9-x-数据源专项实现)。
- `hotspot-discovery`：
  - [x] 核心流程来源于 [03-分阶段功能需求（P0/P1）](./prd/03-features-by-phase-p0-p1.md)。
  - [x] 证据链与降噪要求来自 [risk 与成功指标](./prd/05-risks-and-assumptions.md)。
- `digest-delivery`：
  - [x] 日报与邮件路径来源于 [03-分阶段功能需求（P0/P1）](./prd/03-features-by-phase-p0-p1.md)。
  - [x] 质量目标来源于 [04-成功指标](./prd/04-success-metrics.md)。
- `operator-console`：
  - [x] 浏览、详情与搜索要求来源于 [03-分阶段功能需求（P0/P1）](./prd/03-features-by-phase-p0-p1.md)。

### 6.3 执行顺序

1. 完成 OpenSpec 四类 artifact：proposal、design、specs、tasks（本轮 change）。
2. 同步 `plan.md` 与 `acceptance.md` 阶段交付/验收点到 PRD 子文档条目。
3. 仅保留现有 API 边界内实现，推进控制台基础读链路、日报、邮件链路闭环验收。
4. 用 `openspec validate` 与回归测试确认本轮可交付边界不阻塞。

### 6.4 当前执行进展（2026-04-25）

- 已完成并归档的 OpenSpec 变更：
  - `2026-04-22-codify-requirements-baseline`
  - `2026-04-22-bootstrap-backend-core-skeleton`
  - `2026-04-22-add-read-only-api-assembly`
  - `2026-04-22-add-digest-search-feedback-flows`
  - `2026-04-22-add-worker-digest-delivery`
  - `2026-04-25-mvp-fullchain-execution-2026-04-25`
- 2026-04-25 阶段2实现：`2026-04-25-mvp-stage2-implementation-2026-04-25`（已完成并归档）
- 2026-04-25 阶段3实现：`2026-04-25-mvp-stage3-implementation-2026-04-25`（已完成并归档）
