# HotKey BACKLOG

更新日期：2026-09-30。状态：**Plan 001/002/007/008/031/033/034/035/036/037/039/051 技术完成；Plan058 最小闭环 A 已取得同库真实采集与受控页面证据，但同主题短窗尚未通过，72 小时与真实 Codex 未验收**。逐卡证据见 [Acceptance 002](docs/acceptance/002-信息获取主链路验收.md) 和 [Acceptance 001](docs/acceptance/001-共享运行门槛验收.md)；任务、依赖、FR/NFR/AC 见 [Plan 001—058 索引](docs/plan/README.md)，产品边界见 [PRD 001](docs/prd/001-热点舆情监控平台需求.md) 与 [Design 001](docs/design/001-热点舆情监控平台总体设计.md)。旧 Plan/TASK 从 Git 追溯。

执行方：Codex 实现、受控集成与代码自检；Claude 可参与规划/代码审查；用户负责本人账号、授权与产品决策。用户已要求每个任务结束后提交并推送 main。代码、受控、真实、产品为不同证据等级。

最终目标是整个核心链路 POC，范围以 PRD001 §1 为准。当前第一优先级是 [Plan058](docs/plan/058-M1短窗POC演示与扩围执行计划.md) 的一个主题+HN+一榜最小可演示闭环 A，随后逐项扩为四来源六榜的 M1 短窗 Demo B；分阶段留证，A 不代替 B 或产品验收。日报、周报、Obsidian、知识库检索/问答、报告导出与渠道投递是非核心后续能力，不进入当前排期或阻塞核心链路；009/013真实72小时、正式指标与质量抽检后置。真实Codex请求暂停，受控模型不关闭真实分析或产品AC。

Plan 037 见 Acceptance 002 EV-002-008/014/015：36Kr 快讯固定入口、身份与时间字段、真实双轮原帖、PostgreSQL/Kafka 重放和预算已核对；单来源 `completed`，72 小时父级未通过。

Plan 004 只读覆盖 API 见 Acceptance 002 EV-002-016/043：owner/来源筛选、游标、Job/内容/预算聚合经隔离 PostgreSQL 与运行 OpenAPI 验证；`f6f6b3e7` 远端四项 CI 成功。真实 HN 定时窗与既有真实微博热榜成功窗的 API/Job/内容或快照/预算对账完成，CHK-004-103 通过；两窗跨库，其余三关键词、五榜和 72 小时对账未完成，G5 与本卡仍 `in_progress`。

Plan 007 HN 搜索与重放见 Acceptance 002 EV-002-017：真实 API→Kafka→Worker 两页观察 141 条、入库 111 条；重投无重复内容或预算实耗，远端及本地门禁通过。本卡手动搜索范围 `completed`；定时同窗和 72 小时归 009。

Plan 035 见 Acceptance 002 EV-002-018/044：Google News 双轮各存 87 条、总身份 87；RSS 链接直达原帖，二扫无新身份/版本。预算各 3，尾段部分；技术 `completed`，定时/72 小时归 009，父级 AC 未过。

Plan 036 SearXNG 见 Acceptance 002 EV-002-019：真实两轮各入库 7、总身份 7，MSN 原帖可打开，来源/全局预算各 2；尾段未知，远端三项 CI 通过，本卡 `completed`。

Plan 008 见 Acceptance 002 EV-002-020/021：六榜真实双轮、排名/命中和 Kafka 重放已核对；远端 backend **901 passed/8 skipped**，本卡 `completed`。

Plan 039 见 Acceptance 002 EV-002-022：历史 API/页面读真实双轮快照，桌面及 390px 浏览器通过；本卡 `completed`，72 小时与 Codex 另验。

Plan 040 见 Acceptance 002 EV-002-023/036：旧积压、冻结输入、一次无效补偿与关闭状态已验证；分析候选限主题已选关键词来源或同版本热榜主题命中，`e543cf0c` 远端 backend **949 passed/8 skipped**、contract/runtime 成功。用户暂不发送真实模型请求；十来源真实标注和 60 分钟比例未验，本卡 `in_progress`，AC-002-008 未通过。

Plan 038 见 Acceptance 002 EV-002-024—028/051：HN 评论预设、显式复采、父链、预算与 Kafka 重投有受控证据；本轮修复无尾段证据或采样截断时误报完整覆盖，专项 46 passed、后端 1062 passed/14 skipped。Plan041 已有按钮；逐根真实分页、真实旧帖新回复、操作系统进程重启和十帖待验，`in_progress`。

Plan 041 见 Acceptance 002 EV-002-029—032：评论/作品列表和标注详情 API、页面、旧帖复采按钮经隔离库及桌面/390px 浏览器验证；`4ecced3d` 远端四项 CI 成功。真实 HN 阅读样本与 Codex 产品验收未完成，`in_progress`。

Plan 006 见 Acceptance 002 EV-002-033—038/045—049：采集 v2 计缺失热榜桶；分析候选 v3 按历史提示词启停区间求起点，缺事实列未知。Codex 限流、T0 相位与十来源复算仍缺；`analysis_status=not_computable`、`phase_verified=false`，Plan006/M1 仍 `in_progress`。

Plan 034 见 Acceptance 002 EV-002-039—042：覆盖页面、84 项前端测试及 C/F 门禁通过；真实 HN 定时窗、受控热榜 503 窗和固定快照下钻经浏览器/API/库核对，已确认页中断恢复有先红后绿回归，技术 `completed`。跨库指标不合算；三天共同缺口与 AC-002-006 未通过，真实 Codex 请求关闭。

Plan 051 见 Acceptance 001 EV-001-001—004：隔离源/目标 46 表、1,289 行、74 外键及 MinIO 对象一致；Job/账本重放、失败恢复和损坏/缺对象/错 Schema 拒绝通过。后端全量 956 passed/8 skipped/1 deselected，Ruff/mypy 通过，`TECH-001-051` 技术 `completed`。009/013 最终库需重验；同桶不算独立灾备，产品 AC 未关闭。

Plan058 A 见 Acceptance 002 EV-002-052：隔离库真实 HN 搜索、父链评论、百度 51 条热榜与 3 条主题命中分别可读；受控五类标注状态可见，Worker 真实重启后重投不重复。评论、热榜未同时落在同一主题短窗，09:45 网络预算达到 20/20 后停止调度，A 保持 `in_progress`，B 未开始；远端 `e34c2507` backend/contract/runtime 通过。Plan 005 标注状态与重放受控切片见 Acceptance 002 EV-002-010；旧开发库 3 条异常、真实 Codex 样本未核对，保持 `in_progress`，产品验收不变。

Plan 031 手动运行、到期账本、Job/Outbox 与页面已有 PostgreSQL/Kafka、浏览器证据，技术 `completed`；定时同窗与 72 小时归 009，见 Acceptance 002。

Plan 003 空榜/失败桶受控 PostgreSQL 验证见 Acceptance 002 EV-002-012：合法空榜保留身份、观察与计量，解析/HTTP 错误不造快照，重放不改原事实；032 可在原 Job 重试并累计预算。真实空榜/恢复与热榜 Kafka 重放待验，`in_progress`，AC-002-005/006 未过。

Plan 032 人工重试预算周期经隔离 PostgreSQL/Kafka 和浏览器验证，`bd276c33` 远端四项 CI 成功；真实来源失败→人工重试与 Plan051 保留库核对未完成，`in_progress`，见 Acceptance 002 EV-002-013。

Plan 011 受控风控分类、子进程组回收、来源停用/版本审计及 Web/CLI 本人确认恢复已实现；固定 MediaCrawler 提交 `1bd07bc` 与两阶段补丁精确复现，宿主机预检通过。隔离 PostgreSQL 与浏览器验证、`09d1e135` 远端四项 CI 成功见 Acceptance 003 EV-003-003；真实本人账号恢复留给 012，连续三天留给 013，Plan 011 保持 `in_progress`。

Plan 014 见 Acceptance 004 EV-004-001/002：R1—R5 受控通过，隔离 PG17 全量 **1042 passed/24 skipped**；远端 CI `3220ad87` backend 1058 passed/8 skipped，RG 通过。默认关闭，`in_progress`；真实三平台、人工修订/热度/页面及 M3/AC-004-001 未验收。

## M1—M6 看板

| Design/Epic与Issue | 交付范围 | 当前状态与证据 |
|---|---|---|
| [M1 / 001—009、031—041、058](docs/plan/README.md) | 核心配置/采集/持久化/分析/阅读/覆盖/恢复；058先做同库短窗A再扩围B，AC-002-001—008由009汇总 | 11卡技术completed，003/004/005/006/032/038/040/041/058 in_progress；局部证据见上文。A 已取得真实 HN/百度与受控标注、Worker 重启证据，但同主题短窗未通过；B 未开始，72小时与真实模型产品证据待验 |
| [M2 / Plan 010—013](docs/plan/README.md) | 版本、风控、低频真实、72 小时；AC-003-001—004 | 010 门禁与三版本 Job 快照受控通过；011 分类/停用/人工恢复 POC 受控通过；真实来源关闭，72 小时后置；见 Acceptance 003 |
| [M3 / 014—016、042](docs/plan/README.md) | 事件候选/修订/热度及可操作页面；AC-004-001 | 014 R1—R5 受控通过（EV-004-002），远端 CI 通过，仍 `in_progress`；015/016/042 planned，产品未验收 |
| [M4 / 017—023、043、052](docs/plan/README.md) | 分析质量、主题报告设置（monitor_topics 现有字段）与冻结调度、日报/周报、Obsidian、检索/问答；AC-005-001—008 | planned；部分代码/受控，真实产品验收未过 |
| [M5 / 024—026、044](docs/plan/README.md) | 状态服务、目标/投递页面、SMTP、飞书；AC-006-001 | 024/025/044 planned，真实SMTP仍待凭据/目标授权；026飞书blocked |
| [M6 / 027—030、045—050、053—054](docs/plan/README.md) | 告警/账号、两类导出、公共准入和逐来源调研 | 046—050、053—054 blocked；获准能力还需从059起建实施Plan，FR-007-003/004实际平台承接未就绪 |
| [共享 / 051、055—057](docs/plan/README.md) | 同运行库/Schema恢复、证据生命周期、HTTP契约CI、网页/浏览器底座 | 051 本次隔离库/Schema技术 completed，最终运行库需重验；055/056 planned，057 blocked |

## 当前迭代：先跑通最小 POC Demo

| 顺序 | Plan技术交付 | 工作和门槛 |
|---|---|---|
| 1 / A | 058 最小闭环 | 已在隔离库核对一个主题、HN 与百度热榜的真实采集和页面，以及受控分析、Worker 重启；评论与热榜尚未在同一主题短窗汇齐，人工重试未在该窗验证，预算 20/20 后已停调。下个合法预算窗口复跑，尚未通过 |
| 2 / B | 058 扩围 | A 通过后扩至四关键词来源和六榜，逐入口留证 |
| 核心后续 | M2、M3 | 本人核查后012低频；014→015→016→042事件切片独立推进 |
| 产品后置 | 009/013、正式指标 | 同库同窗72小时、真实模型时效/质量与最终库恢复分别留证 |
| 非核心后置 | 日报/周报/知识库/推送 | 保留规划，不启动新增功能，不作核心前置 |

旧stash未整体应用，未合入草稿不算交付。`hotkey_p1`约4小时的来源/六榜/标注记录和旧库HN线程不可拼接成连续72小时；原始范围见Acceptance002。B站修复后无真实通过证据。

用户后续决策：本人账号核查、真实模型恢复、渠道排期/凭据/目标、后续来源授权与预算；记录到对应Plan后推进依赖步骤。planned文档不等于功能完成，受控技术结果不关闭真实产品AC。
