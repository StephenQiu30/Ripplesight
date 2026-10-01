# HotKey 文档入口

当前 Demo 无需登录注册。产品范围由 PRD 定义，技术约束由 Design 与 PROJECT 定义；历史执行过程通过 Git 查阅。

## 现行文档

| 范围 | 需求 | 设计 |
|---|---|---|
| 总体与 Demo 边界 | [PRD001](prd/001-热点舆情监控平台需求.md) | [Design001](design/001-热点舆情监控平台总体设计.md) |
| 信息获取、阅读与覆盖 | [PRD002](prd/002-信息获取主链路需求.md) | [Design002](design/002-信息获取主链路设计.md) |
| 本人账号 B 站试点 | [PRD003](prd/003-本人账号B站试点需求.md) | [Design003](design/003-本人账号B站试点设计.md) |
| 事件与热度 | [PRD004](prd/004-事件与热度需求.md) | [Design004](design/004-事件与热度设计.md) |
| 报告与知识库 | [PRD005](prd/005-报告与知识库需求.md) | [Design005](design/005-报告与知识库设计.md) |
| 推送 | [PRD006](prd/006-推送需求.md) | [Design006](design/006-推送设计.md) |
| 扩展能力 | [PRD007](prd/007-扩展能力需求.md) | [Design007](design/007-扩展能力设计.md) |

- 当前状态和下一步只维护在 [BACKLOG](../BACKLOG.md)；运行交接见 [HANDOVER](../HANDOVER.md)。
- 技术栈、目录、API 与数据库事实源见 [PROJECT](../PROJECT.md)，执行与检查规范见 [AGENTS](../AGENTS.md)。
- 当前排期的执行任务见 [Plan 入口](plan/README.md)。当前最小演示直接读 [Plan058](plan/058-M1短窗POC演示与扩围执行计划.md)，后置能力和缺口见 BACKLOG。
- 验收证据与未通过条件分别见 [共享运行门槛](acceptance/001-共享运行门槛验收.md)、[信息获取](acceptance/002-信息获取主链路验收.md)、[本人 B 站](acceptance/003-本人账号B站试点验收.md)、[事件与热度](acceptance/004-事件与热度验收.md)。技术通过、受控验证和真实产品验收分别记录。

阅读相关 PRD 与 Design 后，再读正在执行的 Plan；已实现合同直接读 Design，不要求重复阅读历史任务。

## 维护规则

- PRD 写需求与验收标准；Design 写现行合同；Plan 只写当前排期所需步骤；Acceptance 写证据与结论。两个 README 只提供入口，不复制版本号、动态状态、测试数或 AC 映射。
- 完成或合并 Plan 的有效合同进入现行 Design，后置工作回归 PRD/Design/BACKLOG，再删除多余执行文档。未完成和未通过条件保留，删除文件不表示功能完成。历史过程、迁移说明、旧部署快照和截图通过 Git 查阅，不建立 archive 副本。删文档时同步修正链接，不复用旧编号。
- 普通文档整理不另建实施 Plan 或验收文档。代码行为、需求范围、预算或产品验收标准有变化时，仍按所属任务定义合同与验证。
- 正式文档沿用 `NNN-中文主题.md` 和现行同类元数据。PRD/Design/Acceptance 编号分别对应能力范围；Plan 编号独立且不表示执行顺序。Plan 已使用 001—061，新增从 062 继续；Research 已使用至 048，新增从 049 继续。FR/NFR/AC、历史 Plan 与证据编号保持不变。

## 历史查阅

| 移出当前目录的内容 | 现行承接 |
|---|---|
| 已完成 Plan001、002、007、008、031、033—037、039、051、059、061 | 现行合同见 Design001/002；技术与未验边界见 Acceptance001/002，完成状态见 BACKLOG |
| 合并的 M1 子卡与后置能力计划 | 当前执行汇入 058/009；重试与评论保留 032/038，事件候选保留 014；其余需求、合同与未完成条件见 PRD/Design/BACKLOG |
| Research048 及历史验收截图 | 已承接的需求保留在 PRD；调研和图片原文从 Git 查阅，不能作为当前运行证据 |
| 更早的逐项设计、里程碑改号和旧计划 | 现行 PRD/Design；编号迁移过程从 Git 历史查阅 |

本轮清理前的记录可从 `bb4a02e9` 查阅，例如在仓库根目录执行：

```sh
git show bb4a02e9:docs/plan/061-Demo用户体系与历史依赖清理执行计划.md
git show bb4a02e9:docs/acceptance/002-信息获取主链路验收.md
git log --all -- docs
```

历史证据只证明其记录时的代码、数据库和时间窗；不能代替当前就绪、扩围或产品验收。
