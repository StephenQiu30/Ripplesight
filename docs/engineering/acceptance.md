# AI 热点平台验收标准

## 1. 文档结构验收

- [ ] `docs/README.md` 存在并可作为导航页
- [ ] `docs/product/prd.md` 存在
- [ ] `docs/product/plan.md` 存在
- [ ] `docs/research/market-research.md` 存在
- [ ] `docs/engineering/tech-spec.md` 存在
- [ ] `docs/engineering/acceptance.md` 存在
- [ ] `AGENTS.md` 存在
- [ ] 原综合文档不再与上述文档并列作为主事实源

## 2. 产品需求验收

- [ ] PRD 明确产品定位
- [ ] PRD 明确目标用户
- [ ] PRD 明确核心场景
- [ ] PRD 明确本期范围
- [ ] PRD 明确非目标
- [ ] PRD 明确功能分组与优先级
- [ ] PRD 明确成功指标
- [ ] PRD 分拆后的入口页与子文档可相互追踪且覆盖完整章节
- [ ] `docs/product/prd/01-goals-and-positioning.md` 存在
- [ ] `docs/product/prd/02-scope-and-non-scope.md` 存在
- [ ] `docs/product/prd/03-features-by-phase-p0-p1.md` 存在
- [ ] `docs/product/prd/04-success-metrics.md` 存在
- [ ] `docs/product/prd/05-risks-and-assumptions.md` 存在

## 3. 计划文档验收

- [ ] Plan 明确阶段划分
- [ ] 每阶段包含目标、输入、输出、完成标准、主要风险
- [ ] 计划可以直接用于排期讨论
- [ ] 计划中的阶段顺序与产品目标一致

## 4. 市场调研验收

- [ ] Market Research 明确赛道现状
- [ ] Market Research 包含竞品分类与对比
- [ ] Market Research 说明为什么纳入某些来源
- [ ] Market Research 说明为什么当前不纳入某些来源
- [ ] Market Research 明确本项目差异化定位

## 5. 技术方案验收

- [ ] Tech Spec 明确已确认技术选型
- [ ] Tech Spec 不把核心技术路线留给实现者二次选择
- [ ] Tech Spec 明确系统架构与数据流
- [ ] Tech Spec 明确目录职责
- [ ] Tech Spec 明确核心数据模型
- [ ] Tech Spec 明确 API 边界
- [ ] Tech Spec 明确非功能性要求

## 6. X 专项设计验收

- [ ] 明确仅使用官方 X API
- [ ] 明确关键词搜索链路
- [ ] 明确重点账号监测链路
- [ ] 明确趋势词监测链路
- [ ] 明确 `Recent Search` 默认 7 天窗口
- [ ] 明确 `Filtered Stream` 的职责
- [ ] 明确 X 不能单独决定热点总榜
- [ ] 明确进入总榜前需经过标准化、去重、降噪、聚类、评分、摘要、证据回链

## 7. 一致性验收

- [ ] PRD、Plan、Market Research、Tech Spec、Acceptance 中的产品定位一致
- [ ] 技术选型在所有文档中保持一致
- [ ] X 接入方式在所有文档中保持一致
- [ ] MVP 边界在所有文档中保持一致
- [ ] 不存在“产品文档说做、技术文档说不做”的冲突

## 8. 执行可落地验收

- [ ] 研发仅阅读 `PRD + Tech Spec + Acceptance` 即可进入详细设计
- [ ] 产品仅阅读 `README + PRD + Plan + Market Research` 即可完成范围确认与阶段评审
- [ ] 文档已足够支撑后续实现，不需要再次决定核心路线

## 9. 阶段性交付验收

### 阶段 1

- [ ] 文档体系冻结（[docs/product/prd.md](../product/prd.md) 与 [docs/README.md](../README.md)）
- [ ] 产品定位与目标用户可追溯：[01-目标与定位](../product/prd/01-goals-and-positioning.md)
- [ ] 范围与非目标明确：[02-范围与非目标](../product/prd/02-scope-and-non-scope.md)
- [ ] OpenAPI 契约基线存在且未因本轮变更新增接口：[contracts/openapi/openapi.yaml](../../contracts/openapi/openapi.yaml)
- [ ] 新增字段/API 改动追溯到主链路文档与验收：见 [AGENTS.md](../../AGENTS.md)

### 阶段 2

- [x] 来源治理与采集边界在 PRD 一期范围内： [02-范围与非目标](../product/prd/02-scope-and-non-scope.md)
- [x] `RawContentItem` 标准化与来源追溯可验证：[03-分阶段功能需求（P0/P1）](../product/prd/03-features-by-phase-p0-p1.md)

### 阶段 3

- [x] 去重、聚类、评分规则在 MVP 一阶段可追溯：[03-分阶段功能需求（P0/P1）](../product/prd/03-features-by-phase-p0-p1.md)
- [x] X 不能单独决定总榜并经过标准化→去重→聚类→评分： [03-分阶段功能需求（P0/P1）](../product/prd/03-features-by-phase-p0-p1.md)、[03-分阶段功能需求（P0/P1）-范围约束](../product/prd/02-scope-and-non-scope.md)

### 阶段 4

- [ ] 日报生成、中文摘要与邮件投递路径可追溯：[03-分阶段功能需求（P0/P1）](../product/prd/03-features-by-phase-p0-p1.md)
- [ ] 邮件状态可追踪：[04-成功指标](../product/prd/04-success-metrics.md) 与 [03-分阶段功能需求（P0/P1）](../product/prd/03-features-by-phase-p0-p1.md)

### 阶段 5

- [ ] 控制台热点榜、事件详情、来源追踪可追溯：[03-分阶段功能需求（P0/P1）](../product/prd/03-features-by-phase-p0-p1.md)
- [ ] 搜索与反馈闭环可追溯：[03-分阶段功能需求（P0/P1）](../product/prd/03-features-by-phase-p0-p1.md)
