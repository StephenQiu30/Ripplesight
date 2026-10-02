# HotKey 文档入口

公开首页为 SEO Welcome，账号密码、GitHub 或邮箱验证码登录后进入工作区。Python/FastAPI、Next.js 和 Kafka 承载信息获取、分析、事件、报告、公开阅读、模型榜、公告与运营能力；业务库统一为 `hotkey`。需求、实现和真实产品验收分别维护。

## 现行文档

| 范围 | 需求 | 设计 |
|---|---|---|
| 总体与 Demo | [PRD001](prd/001-热点舆情监控平台需求.md) | [Design001](design/001-热点舆情监控平台总体设计.md) |
| 信息获取、阅读与覆盖 | [PRD002](prd/002-信息获取主链路需求.md) | [Design002](design/002-信息获取主链路设计.md) |
| 本人账号 B 站试点 | [PRD003](prd/003-本人账号B站试点需求.md) | [Design003](design/003-本人账号B站试点设计.md) |
| 事件与热度 | [PRD004](prd/004-事件与热度需求.md) | [Design004](design/004-事件与热度设计.md) |
| 报告与知识库 | [PRD005](prd/005-报告与知识库需求.md) | [Design005](design/005-报告与知识库设计.md) |
| 推送 | [PRD006](prd/006-推送需求.md) | [Design006](design/006-推送设计.md) |
| 扩展能力 | [PRD007](prd/007-扩展能力需求.md) | [Design007](design/007-扩展能力设计.md) |
| 完整业务范围与跨域合同 | [PRD046](prd/046-AIHOT全量业务迁移需求.md) | [Design048](design/048-AIHOT全量迁移架构与兼容设计.md) |

- [PROJECT](../PROJECT.md) 维护技术、目录、API 和数据库约束；[AGENTS](../AGENTS.md) 维护工程检查。
- [BACKLOG](../BACKLOG.md) 维护当前状态与缺口；[HANDOVER](../HANDOVER.md) 维护运行交接；[Plan 索引](plan/README.md) 提供当前执行入口。
- 证据见 [共享运行门槛](acceptance/001-共享运行门槛验收.md)、[信息获取](acceptance/002-信息获取主链路验收.md)、[本人 B 站](acceptance/003-本人账号B站试点验收.md)、[事件与热度](acceptance/004-事件与热度验收.md)。
- 上游固定版本、复制资产及完整许可见 [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md)。

## 维护规则

PRD 写需求与验收标准；Design 写现行合同；Plan 只写当前仍需执行的步骤；Acceptance 写实际证据。已承接的调研、完成步骤、旧部署快照和历史截图从 Git 查询，不保留另一份档案或进度表。移除历史文档不关闭未通过的验收。

文档采用 `NNN-中文主题.md`；旧 FR/NFR/AC、证据和文档编号保持含义。Plan 已使用至 063，新增从 064 继续；Research 已使用至 050，新增从 051 继续。普通整理不新建 Plan 或验收文件。

## 历史查阅

AIHOT 源码调研 049/050 和本次清理前的实现记录可从 `d11db4f5` 查询；更早的计划和设计用 `git log --all -- docs` 查阅。历史证据只证明记录时的代码、数据库和时间窗。

```sh
git show d11db4f5:docs/research/050-AIHOT全量源码与迁移覆盖矩阵.md
git log --all -- docs
```
