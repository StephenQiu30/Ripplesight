# PLAN009 AIHOT参考对齐偏差计划

更新日期：2026-10-05，Asia/Shanghai。本文件按用户要求新建，记录 HotKey 现行实现与参考项目 [AIHOT](https://github.com/KKKKhazix/AIHOT) 的偏差、处理建议和工作包。需求定义仍以各 PRD 为准，技术合同以所属 Design 为准，总体进度只在 [BACKLOG](../../BACKLOG.md) 汇总，实际证据进入既有 Acceptance。计划写成不等于偏差已消除；各 WP 均未开始。

## 1. 范围与非目标

范围：逐领域对比 AIHOT 上游与 HotKey 的信源/采集、预筛与评分精选、结构抽取与写作、事件关系、事件综述、热度、日周月刊、公开出口、后台运营，以及模型榜/Codex 监控；给出偏差类型、影响、建议和可验收的修正工作包。

非目标：

- 不迁移 Node/pg-boss/React Router，不启动第二个 AIHOT 实例，不复制 AIHOT 品牌、Logo、信源名单或运营数据。
- 不因对齐上游而放宽 HotKey 现有边界：按 owner 的发布分区、Job/Outbox/Kafka、ALL 许可复验、零付费、真实 Codex/付费请求暂停、unknown 不自动重付（[Design007](../design/007-扩展能力设计.md) AIHOT参考行）。
- 本计划不直接修改 PRD/Design 的 FR/AC；需改合同的列为 WP，由执行时先改所属 Design 再改代码。

## 2. 对比基线

| 基线 | 提交 | 日期 | 说明 |
|---|---|---|---|
| HotKey 已移植固定点 | `035f7b7f6e26cf203562ddd6065ff7adc1bb0c07` | 2026-10-01 | [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md)、publication/leaderboard 的 PROVENANCE 记录的唯一改编来源 |
| PRD007 只读核验点 | `85a550f2b2c121e0a9f53f93f96150380b29f936` | 2026-10-04 | [PRD007 §8.6](../prd/007-扩展能力需求.md) 只用于七平台路线核验，未升级代码 |
| 本次对比上游 HEAD | `9acad0c3d7687d9210c2b7774f83799dfd36734b` | 2026-10-05 | 距固定点 27 个提交、641 个文件变化，含 4.0.0 结构调整 |

已核实一致（不列为偏差）：

- `backend/app/analysis/prompt_templates/` 的 27 个提示词与固定点 `industry/prompts/` 逐字一致。
- 精选门槛 T1 60 / T1_5 65 / T2 76、`understandFloor` 50 与上游 HEAD 相同（[editorial_rules.py:26](../../backend/app/analysis/editorial_rules.py)）。
- 热度 `heat-v1-48h-halflife24h`：48 小时窗口、每个独立参与者计一次、24 小时半衰、与 6 小时前比较、至少 2 个参与者且含精选组（[attention.py](../../backend/app/events/attention.py) 与上游 `packages/backend/src/events/hot.ts`）。
- 事件召回 14 天窗口与 `GROUP_REVIEW_MODEL` 式复核（[consolidation.py](../../backend/app/events/consolidation.py)、[signals.py](../../backend/app/events/signals.py)）。

## 3. 偏差总表

偏差类型：**A** 固定点之后上游新变化，HotKey 未同步；**B** 移植不一致或遗漏；**C** HotKey 有意差异，有现行合同依据。建议：同步 / 不同步 / 待用户决定 / 待核实。

| 编号 | 领域 | 上游依据 | HotKey 现状 | 类型 | 影响 | 建议 |
|---|---|---|---|---|---|---|
| D-01 | 精选 | HEAD `docs/selection.md` 第6步、`tests/selected-news-gate.test.ts`：够分后等归组完成，模型判断是否与精选已有报道为同一新闻、有无新信息；无新信息不进精选，失败停留并告警 | 未发现等价“精选重复/新信息”闸门；入选只看两次评分与门槛 | A | 同一新闻换说法重复入选，精选与日报重复 | 同步（WP-009-03） |
| D-02 | 结构抽取 | HEAD `industry/prompts/structure.md`：新增 `scope`(single/composite/unknown)、当前动作与背景区分、`fact.evidence` 与 `conditions` 原文摘录 | 模板仍为固定点版本；输出无 scope/evidence/conditions | A | 综合稿被当单事件归组；事实缺原文出处与适用条件 | 同步（WP-009-02），涉及 analysis Schema 与 events 事实合同 |
| D-03 | 事件关系 | HEAD `group-definitions.md`/`group-method.md`/`group-pair.md`/`group-batch.md`：SAME_OCCURRENCE 须落到具体对象，SAME_STORY 不能仅凭同产品同周期，ROUNDUP 扩至大会回顾/产品总览/会议综述 | 模板为固定点版本，[relations.py](../../backend/app/events/relations.py) 使用 group-pair | A | 同公司同日多发布被误并；综合稿与单事件误合 | 同步（WP-009-02），需重跑关系评测 |
| D-04 | 事件综述 | HEAD `story-digest.md`：改为“事件概览”，结论先行、100–300 字、1–3 段，删除 `latest` | [digest.py:40/199](../../backend/app/events/digest.py) 使用内置提示词 `events-digest-v1-facts`，输出 `latest_progress`；复制的 story-digest.md 未被调用 | B+A | 概览写法与上游不同；模板与实际调用不一致，提示词哈希/版本无法溯源 | 待用户决定：改用上游模板或保留内置并删除未用模板（WP-009-04） |
| D-05 | 日报成刊 | HEAD `docs/selection.md` 第7步、`packages/backend/src/reports/edition.ts`：日报按规则编排、不调模型；一件事一条、近7期去重、跟进门槛（当事方新动作或≥4家信源）、官方原帖+≥3参与方补入、前12条正文/同源≤2/快讯≤10、头条与2–4条看点；删除 report-daily-lead | [edition_compose.py:22/35](../../backend/app/reports/edition_compose.py) 仍调用 report-daily-lead；[edition_rules.py](../../backend/app/reports/edition_rules.py) 每分类8条+12快讯，按事实去重 | A | 日报质量规则落后；模型启用时多一次调用 | 待用户决定是否改为不调模型（WP-009-05） |
| D-06 | 周刊/月刊 | HEAD：由日报汇编，同一事件跨天算一件，按日报位置/报道面/评分排序，周20件、月30件；新增 report-period-sections / no-sections，模型只写总述与栏目导读并做名称/数字越界检查 | 周40、月60，直接从精选候选排序；只用 report-period | A | 周月刊与日报脱节，篇幅偏长 | 同步（WP-009-05） |
| D-07 | 刊期时间 | 上游日报 08:00（前日08:00—当日08:00）、周一10:00、每月1日10:30，`site.ts` 的 `EDITION_TIMES` | [Design008](../design/008-完整业务设计.md) 与 edition_rules.py：北京自然日/ISO周/自然月，09:00 到期 | C | 刊期边界与上游不同，但与个人日周报口径一致 | 不同步；保持 Design008 |
| D-08 | 首次导入 | HEAD 50b562b：首次导入后 RSS/网页列表/JSON 只收信源加入前48小时以内或之后的条目，无日期照收 | [editorial_registry.py:109](../../backend/app/sources/editorial_registry.py) 按 `initial_backfill_months`/`initial_backfill_limit` 截取 | 待核实 | 首次导入可能把订阅存档当新内容逐条分析 | 待核实后决定（WP-009-06） |
| D-09 | 无日期资料 | HEAD 50b562b：无可信发布时间的新资料先不进公开列表/精选/报告/热点/推送，读到原文日期后再判断；出口标“收录时间” | [PRD002](../prd/002-信息获取主链路需求.md) 允许“明确标注的发现时间”；精选/热点/推送对无日期资料的处理待核实 | 待核实 | 旧文以新文身份刷屏 | 待核实（WP-009-06） |
| D-10 | 日期解析 | HEAD 309e32e/6560d7f/561b880：Atom 纯文本按原文、英文日期不受夏令时影响、JSON 坏日期不中断整批、无时区按信源时区、历史日期审计更正 | RSS 适配器正在修改；上述逐项未核对 | A | 个别信源整批失败或时间错位 | 同步（WP-009-06），以上游测试用例为样本 |
| D-11 | 分类/标签 | HEAD `industry/taxonomy.ts` 68 行变化；structure.md 新增“模型发布/评测/产品更新”等标签使用规则 | 分类表沿用固定点 | A | 分类与标签口径不一致 | 同步（WP-009-02） |
| D-12 | 推理模型额度 | HEAD 50b562b：`LLM_REASONING_TOKENS`/具名模型 `reasoningTokens`，额度用尽报 `finish_reason=length` | 未发现等价配置 | A | 启用推理模型时输出被截断难诊断 | 同步，低优先级（WP-009-07）；真实模型调用仍暂停 |
| D-13 | 公开出口 | HEAD ec42ff7/1d48ec1/50b562b/dd12db1/36604b9/9acad0c：更正/撤回/缓存一致性、公开分类筛选 `PUBLIC_CATEGORIES`、MCP 订阅共享通道与容量上限、请求体上限、图片缓存与 SVG 选择、分享图预热 | 固定点版本的 publication；HotKey 另有 ALL 许可复验 | A | 公开出口局部行为落后 | 逐项评估后同步不冲突部分（WP-009-07） |
| D-14 | 模型榜 | 4.0.0（1ca5d6d）将模型榜移出开源框架 | 保留基于固定点的 [leaderboard](../../backend/app/leaderboard/PROVENANCE.md)，PRD008 有需求 | C | 无法再从上游获得更新，后续自行维护 | 待用户决定是否保留 |
| D-15 | Codex 重置监控 | 4.0.0 移出框架 | 保留 `monitors/codex_*` 与 codex_reset 订阅 | C | 同上 | 待用户决定是否保留 |
| D-16 | 主题大事记 | 4.0.0 移出框架 | 未发现对应实现 | C | 无 | 不同步 |
| D-17 | 站点配置组织 | 4.0.0/d5d9645：站点项迁入 `site/`，专属功能放 `modules/` | HotKey 使用 Python 领域目录与 `HOTKEY_` 配置 | C | 无 | 不同步；仅借鉴文案集中定义 |
| D-18 | 未用模板 | — | group-batch.md、group-signal.md、story-digest.md 已复制但无代码调用 | B | 维护者误以为生效；与 THIRD_PARTY_NOTICES 描述不符 | 随 WP-009-02/04 决定接入或删除，并同步声明 |
| D-19 | 改编溯源 | — | THIRD_PARTY_NOTICES 与两份 PROVENANCE 仍指固定点；PRD007/Design007 另记 85a550f | B | 多个参考 SHA 并存，来源不清 | 同步（WP-009-01） |

统计：共 19 项。A 类 9 项（D-01—03、D-05、D-06、D-10—13），B 类 2 项（D-18、D-19），A+B 1 项（D-04），C 类 5 项（D-07、D-14—17），待核实 2 项（D-08、D-09）。

## 4. 工作包

状态统一为 `planned`。每个 WP 先补所属 Design 合同，再改代码；验证按 [AGENTS](../../AGENTS.md) 的后端/前端检查执行，真实模型调用继续暂停，评测在受控样本或已有回执上进行。

| WP | 内容 | 依赖 | 状态 |
|---|---|---|---|
| WP-009-01 | 参考基线与溯源 | 用户决定 §6-1 | planned |
| WP-009-02 | 结构抽取与事件关系提示词 | 01 | planned |
| WP-009-03 | 精选重复与新信息闸门 | 02 | planned |
| WP-009-04 | 事件综述 | 01、用户决定 §6-3 | planned |
| WP-009-05 | 日周月刊编排 | 02、03、用户决定 §6-2 | planned |
| WP-009-06 | 首次导入与日期规则 | 01 | planned |
| WP-009-07 | 公开出口与模型额度修复 | 01 | planned |

### WP-009-01 参考基线与溯源

- 输入：本计划 §2、上游 HEAD 与固定点；用户对是否升级固定点的决定。
- 输出：选定新的固定提交；更新 THIRD_PARTY_NOTICES、publication/leaderboard PROVENANCE 与 PRD007/Design007 中的 SHA 说明，使改编来源只有一处权威记录。
- 目标路径：`THIRD_PARTY_NOTICES.md`、`backend/app/*/PROVENANCE.md`、`docs/design/007-扩展能力设计.md`。
- 非目标：不复制上游品牌、Logo 或信源数据。
- 风险：许可文本遗漏；HEAD 删除了模型榜，改编来源需区分“沿用固定点”与“同步 HEAD”。
- 验收：每个改编模块都能对应到唯一上游 SHA 和路径；MIT 与 OFL 文本完整保留；本地链接检查与 `git diff --check` 通过。

### WP-009-02 结构抽取与事件关系提示词

- 输入：D-02、D-03、D-11、D-18；上游 HEAD `industry/prompts/`、`industry/taxonomy.ts`。
- 输出：同步 structure 与 group-* 模板；analysis 结构输出增加 `scope`、`fact.evidence`、`fact.conditions`，程序校验摘录可在原文连续查到、composite 时 fact 为 null；events 事实合同保存 evidence/conditions；分类与标签按新规则更新。未接入的 group-batch/group-signal 二选一：接入或删除并更新声明。
- 目标路径：`backend/app/analysis/prompt_templates/`、`analysis/editorial_rules.py`、`analysis/editorial_schemas.py`、`events/fact_*.py`、`backend/database/schema.sql`（如需）、对应 Design004/Design008。
- 非目标：不重算已完成的历史分析；提示词版本按内容哈希自然生效。
- 风险：Schema 变更须走 DDL/ORM/断言同批；输出变长影响预算。
- 验收：单元测试覆盖 single/composite/unknown、主帖评测引用旧发布、介绍既有功能、拼接引文被丢弃等上游样例；关系评测（evaluation_relations）在同一批成对样本上与旧模板并排输出准确率，composite 与单事件不再判为 SAME_OCCURRENCE/SAME_STORY；后端四项检查通过。

### WP-009-03 精选重复与新信息闸门

- 输入：D-01；上游 HEAD `docs/selection.md` 第6步及 `tests/selected-news-gate.test.ts`。
- 输出：够分资料在归组完成后，由模型判断是否与已有精选为同一新闻、是否带来新信息；同一新闻多篇折为阅读组并由代表报道出面（官方一手优先），无新信息或无法确认的不进精选；确认失败停留并超过10分钟告警，后台可重新归组。
- 目标路径：`backend/app/analysis/editorial_*`、`events/relations.py`、`publication/projection.py`、`operations` 告警、Design008。
- 非目标：SelectBench 评测仍只跑预筛与两次评分，不含此闸门。
- 风险：增加一次模型调用；停留资料需可见、可人工恢复，不能自动放行。
- 验收：受控样本中同一新闻换说法的第二篇不进精选、带新信息的跟进入选、模型失败时停留并产生告警；API/RSS 每条新闻只出一条代表报道；后端检查通过。

### WP-009-04 事件综述

- 输入：D-04、D-18；用户决定 §6-3。
- 输出（若采用上游）：digest 改用 story-digest.md 渲染，输出 title/digest，移除或保留兼容的 `latest_progress`（需同步 API Schema 与前端）；提示词版本改为模板哈希。若保留内置：删除未用的 story-digest.md 并在 THIRD_PARTY_NOTICES 说明。
- 目标路径：`backend/app/events/digest.py`、`events/schemas.py`、`frontend/src/api`（生成）、Design004。
- 风险：OpenAPI 变更需按 AGENTS 顺序生成客户端。
- 验收：同一批事件上新旧提示词并排输出（参照上游 `docs/story-digest-evaluation.md`），首句含核心变化与结论、100–300 字、1–3 段；`pnpm openapi:check` 与前后端检查通过。

### WP-009-05 日周月刊编排

- 输入：D-05、D-06；用户决定 §6-2；保持 D-07 的自然日/09:00 刊期（Design008）。
- 输出：日报按上游规则编排（一件事一条、近7期去重与跟进门槛、官方原帖补入、正文12条/同源≤2/快讯≤10、头条与看点）；是否删除 report-daily-lead 调用由 §6-2 决定。周刊/月刊由日报汇编，周20、月30件，引入 report-period-sections/no-sections，模型输出名称/数字越界时回退模板句。
- 目标路径：`backend/app/reports/edition_rules.py`、`edition_compose.py`、`edition_services.py`、`analysis/prompt_templates/`、Design008。
- 非目标：不改刊期时间；不影响个人 `report.daily`/`report.weekly`。
- 风险：编排依赖 WP-009-02/03 的 scope 与精选闸门；历史刊期不重写。
- 验收：以固定候选集的单元测试复算上游规则各分支；模型关闭时日周月刊可完整生成；越界名称/数字触发回退；后端检查通过。

### WP-009-06 首次导入与日期规则

- 输入：D-08、D-09、D-10；上游 50b562b、309e32e、6560d7f、561b880 及 `tests/` 中对应日期用例。
- 输出：先核实 HotKey 首次导入与无日期资料在精选、报告、热点、推送中的行为并记录结论；确认缺口后实现“信源加入前48小时”截取（或在 Design002 写明保留现行回填策略的理由）、无可信日期不进公开派生出口、Atom 纯文本、夏令时、坏日期不中断整批、无时区按信源时区。
- 目标路径：`backend/app/sources/editorial_*`、`sources/adapters/editorial_*`、Design002。
- 风险：当前工作区已有 `editorial_rss.py` 未提交修改，执行前需与其归属方协调。
- 验收：移植上游日期相关用例为 pytest 并通过；首次导入受控样本不产生存档内容的分析任务；后端检查通过。

### WP-009-07 公开出口与模型额度修复

- 输入：D-12、D-13。
- 输出：逐提交评估上游公开出口修复，与 HotKey ALL 许可复验、ETag/304、撤回逻辑不冲突的部分同步；新增推理模型输出额度配置（`HOTKEY_` 前缀）与明确的截断错误。
- 目标路径：`backend/app/publication/`、`backend/app/ai/`、`.env.example`、Design008。
- 风险：缓存一致性修复可能与现有复验路径重复。
- 验收：每项同步或不同步都有一行结论；相关公开读取测试与后端、前端检查通过。

## 5. 执行顺序

01 → 02 → 03 → 05；04、06、07 在 01 完成后可并行。每个 WP 完成后在本节记录结果与验证命令输出摘要，BACKLOG 只更新总览一行。

## 6. 需要用户决定

1. 是否把固定提交从 `035f7b7` 升级到上游 HEAD `9acad0c`（或更新的提交），作为后续同步基线。
2. 公开日报是否改为按规则编排、不调用模型（上游做法），还是保留 report-daily-lead 模型导语。
3. 事件综述改用上游“事件概览”模板并移除 `latest_progress`，还是保留 HotKey 内置提示词。
4. 上游已移出框架的模型榜与 Codex 重置监控，是否继续由 HotKey 自行维护。
