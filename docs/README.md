# HotKey 文档

## 阅读与维护入口

先从用户要获得的结果选择PRD，再阅读同领域Design；实施顺序和未完成状态只到 [BACKLOG](../BACKLOG.md) 核对，真实证据只到Acceptance核对。PRD/Design描述交付合同，文件存在与页面入口不代表能力已上线。

| 当前用户任务 | 主要合同 | 验证入口 |
|---|---|---|
| 不登录也能读持续更新的真实公开信息 | PRD002 FR-002-015 / Design002 §3.7；Design001 §9.2；Design048公开许可 | AC-002-015及信息获取Acceptance；公开owner、模型关闭、撤回与匿名读取分别验证 |
| 登录后按关键词找到材料和支持来源的评论 | PRD002主题/来源/评论；PRD005 FR-005-012；PRD001账户边界 | AC-005-013、信息获取与共享Acceptance；不将热榜、评论数或试点当全平台能力 |
| 获得可核查的个人日报/周报 | PRD005 / Design005 §3.2.3；自然日与ISO周独立 | PRD005对应AC与BACKLOG；个人周报/模板待分析清单仍待实现，公共周刊独立 |
| 阅读公开日周月刊或模型榜 | PRD046 / Design048；Frontend DESIGN公开阅读合同 | 各领域AC、公开分区与当前许可；私人UUID报告、编选与管理继续鉴权 |

## 领域文档索引

| 范围 | 需求 | 设计 |
|---|---|---|
| 总体、账户与信息监控 | [PRD001](prd/001-热点舆情监控平台需求.md) | [Design001](design/001-热点舆情监控平台总体设计.md) |
| 获取、阅读与覆盖 | [PRD002](prd/002-信息获取主链路需求.md) | [Design002](design/002-信息获取主链路设计.md) |
| 本人 B站试点 | [PRD003](prd/003-本人账号B站试点需求.md) | [Design003](design/003-本人账号B站试点设计.md) |
| 事件与热度 | [PRD004](prd/004-事件与热度需求.md) | [Design004](design/004-事件与热度设计.md) |
| 报告与知识库 | [PRD005](prd/005-报告与知识库需求.md) | [Design005](design/005-报告与知识库设计.md) |
| 通知 | [PRD006](prd/006-推送需求.md) | [Design006](design/006-推送设计.md) |
| 扩展能力 | [PRD007](prd/007-扩展能力需求.md) | [Design007](design/007-扩展能力设计.md) |
| 完整业务 | [PRD046](prd/046-完整业务需求.md) | [Design048](design/048-完整业务设计.md) |

[PROJECT](../PROJECT.md) 维护技术/架构，[AGENTS](../AGENTS.md) 维护工程检查，[BACKLOG](../BACKLOG.md) 维护状态与执行顺序，[Web DESIGN](../frontend/DESIGN.md) 维护视觉规范。验收证据分别见 [共享门槛](acceptance/001-共享运行门槛验收.md)、[信息获取](acceptance/002-信息获取主链路验收.md)、[B站](acceptance/003-本人账号B站试点验收.md)、[事件](acceptance/004-事件与热度验收.md)。上游版本与资产许可见 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)。

## 变更归属与证据

PRD 只写需求/AC，Design 只写现行合同，状态只写 BACKLOG，证据只写 Acceptance。文档采用 `NNN-中文主题.md`，现有编号和FR/NFR/AC含义不变；编号不复用。已完成步骤、临时运行快照、视觉参考、调研和版本迁移过程从 `git log --all -- docs` 查阅；文件清理不取消需求或改变未通过结论。

整理按“用户问题→既有FR/AC→设计职责/组件与状态→真实证据”映射，先修冲突和缺失条件，不复制第二份路线或通过清空旧文档关闭需求。没有访谈重要性/满意度、触达人数与工时数据时，优先级采用需求对齐、源码缺口和依赖风险的定性判断，执行顺序仍唯一维护在BACKLOG。
