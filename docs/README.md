# HotKey 文档

## 1. 按任务找文档

先按要完成的用户结果找 PRD，再读同号 Design；进度只看 [BACKLOG](../BACKLOG.md)，证据只看 Acceptance。文件存在、页面入口或受控测试不代表能力已上线。

| 用户任务 | 需求与设计 | 验收 |
|---|---|---|
| 不登录阅读持续更新的公开信息 | PRD002 FR-002-015；Design002 §3.7；Design001 §9.2；Design008 公开许可 | AC-002-015 |
| 登录后按关键词找到材料与评论 | PRD002；PRD005 FR-005-012；PRD001 §3 账户 | AC-005-013 及 PRD002 对应 AC |
| 获得可核查的个人日报/周报 | PRD005；Design005 §3.2.3 | PRD005 AC；公共刊物不替代个人周报 |
| 阅读公开日周月刊或模型榜 | PRD008；Design008；[Web DESIGN](../frontend/DESIGN.md) | PRD008 AC |
| 试用本人 B 站资料 | PRD003；Design003 | AC-003-001—004 |
| 分辨同一事件、新进展与热度 | PRD004；Design004 | PRD004 AC |
| 在本地笔记找回资料并提问 | PRD005 FR-005-006—007；Design005 | AC-005-004、006、008 |
| 收到已生成的报告 | PRD006；Design006 | AC-006-001 |
| 追踪作者、导出、告警、扩来源与七平台 | PRD007；Design007 §11；PLAN007；Research007 | AC-007-001—016 |
| 与参考项目 AIHOT 对齐 | PLAN009 | 偏差逐项依据与 WP 验收 |
| 维护模型榜、公告、媒体与运营恢复 | PRD008 FR-008-001—009；Design008 | AC-008-001—009 |

## 2. 文档索引

| 编号 | 领域 | 需求 | 设计 | 计划 / 调研 | 验收 |
|---|---|---|---|---|---|
| 001 | 总体、账户与共享规则 | [PRD001](prd/001-热点舆情监控平台需求.md) | [Design001](design/001-热点舆情监控平台总体设计.md) | — | [Acceptance001 共享运行门槛](acceptance/001-共享运行门槛验收.md) |
| 002 | 信息获取与阅读 | [PRD002](prd/002-信息获取主链路需求.md) | [Design002](design/002-信息获取主链路设计.md) | — | [Acceptance002](acceptance/002-信息获取主链路验收.md) |
| 003 | 本人 B 站试点 | [PRD003](prd/003-本人账号B站试点需求.md) | [Design003](design/003-本人账号B站试点设计.md) | — | [Acceptance003](acceptance/003-本人账号B站试点验收.md) |
| 004 | 事件与热度 | [PRD004](prd/004-事件与热度需求.md) | [Design004](design/004-事件与热度设计.md) | — | [Acceptance004](acceptance/004-事件与热度验收.md) |
| 005 | 报告与知识库 | [PRD005](prd/005-报告与知识库需求.md) | [Design005](design/005-报告与知识库设计.md) | — | 记入 Acceptance001 |
| 006 | 推送 | [PRD006](prd/006-推送需求.md) | [Design006](design/006-推送设计.md) | — | 记入 Acceptance001 |
| 007 | 扩展能力与七平台 | [PRD007](prd/007-扩展能力需求.md) | [Design007](design/007-扩展能力设计.md) | [PLAN007](plan/007-公开信息免费采集执行计划.md)；[Research007](research/007-七平台与竞品调研.md) | 记入 Acceptance001/002 |
| 008 | 完整业务 | [PRD008](prd/008-完整业务需求.md) | [Design008](design/008-完整业务设计.md) | — | 记入所属 Acceptance |
| 009 | AIHOT 参考对齐 | — | — | [PLAN009](plan/009-AIHOT参考对齐偏差计划.md) | 按 WP 记入所属 Acceptance |

其他权威文档：[PROJECT](../PROJECT.md)（技术与目录）、[AGENTS](../AGENTS.md)（工程检查）、[BACKLOG](../BACKLOG.md)（进度）、[Web DESIGN](../frontend/DESIGN.md)（视觉）、[THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)（上游版本与许可）。

## 3. 写在哪里

| 内容 | 唯一位置 | 不写的内容 |
|---|---|---|
| 用户问题、范围、FR/NFR/AC、产品决策 | PRD | 实现状态、证据、日期快照 |
| 现行技术合同：领域、接口、事务、数据、任务、错误 | Design | 进度、证据、产品决策 |
| 工作包、依赖、checklist（仅用户明确要求独立计划时） | PLAN | 第二份需求或证据 |
| 外部资料、平台与竞品调研快照 | Research | 需求或验收结论 |
| 总体进度、执行顺序、剩余条件 | BACKLOG | WP 细节（已有 PLAN 时） |
| 实际证据与未通过条件 | Acceptance | 计划或预测 |

- 共享规则只在一处定义，其他文档引用编号（如 NFR-001-103、DEC-001-213），不复制原文。
- 临时实施过程、运行快照、视觉参考和版本迁移从 `git log -- docs` 查阅，不另存文档；清理文件不取消需求或改变未通过结论。
- 优先级没有访谈、触达或工时数据时用定性判断，不编造分数或工期。

## 4. 编号规则

- **文件**：`<类型>/NNN-中文主题.md`。PRD 与 Design 同号成对，PLAN、Research、Acceptance 使用所属领域编号；跨领域的新文档取下一个未用领域号（当前下一个为 010）。标题以 `PRD00N`/`Design00N`/`PLAN00N`/`Research00N` 开头。
- **条目**：`FR/NFR/AC/BR-<领域号>-<序号>`；`DEC/OPEN` 为 `DEC-001-xxx`（产品决策只在 PRD001 §8）；工作包 `WP-<计划号>-<序号>`；证据 `EV-<验收号>-<序号>`；BACKLOG 工作代号 `BL-NN`。
- 编号一经发布不复用。**证据编号 EV 永不重编号**，以免证据与历史提交失联。

### 4.1 2026-10-05 重编号对照

| 旧编号 | 新编号 |
|---|---|
| `prd/046-完整业务需求.md`、PRD046、FR-046-xxx、AC-046-xxx | `prd/008-完整业务需求.md`、PRD008、FR-008-xxx、AC-008-xxx |
| `design/048-完整业务设计.md`、Design048 | `design/008-完整业务设计.md`、Design008 |
| `plan/064-AIHOT参考对齐偏差计划.md`、PLAN064、WP-064-xx | `plan/009-AIHOT参考对齐偏差计划.md`、PLAN009、WP-009-xx |
| 原 PRD007 §8 平台与市场调研 | `research/007-七平台与竞品调研.md`（Research007） |
| BACKLOG 任务 063 / 062 / 058 / 032 / 038 / 009 / 014 | BL-01 账户与登录 / BL-02 完整业务 / BL-03 M1 短窗 / BL-04 人工重试 / BL-05 HN 评论 / BL-06 M1 正式窗口 / BL-07 事件候选 |
| 原 044 模型平台采集、045 模型联网检索 | 不再编号，见 DEC-001-106 |
| CHK-058-101—104 | CHK-BL03-101—104 |

其余编号（PRD/Design 001—007、Acceptance 001—004、FR/NFR/AC/BR/DEC/OPEN、EV、WP-007）未变。PRD001 章节已重排：原 §2.1 账户 → §3，原 §5 共享 NFR → §6，原 §9 决策 → §8。
