# HotKey Server 交接

更新日期：2026-09-30。本文件只记录当前实现快照（≤5 KB）；需求见 [PRD 001 v5.1](docs/prd/001-热点舆情监控平台需求.md)，Epic 设计见 [Design 001 v4.0](docs/design/001-热点舆情监控平台总体设计.md) 及对应 Design，任务与证据见 [逐 Issue Plan 索引](docs/plan/README.md) 和 [BACKLOG](BACKLOG.md)。

## 当前边界

- 当前最终目标是整个核心链路 POC，范围见 PRD001 §1；先按 Plan058 跑通一个主题、HN 公开搜索和一榜的同库最小演示，再扩至四关键词来源、HN 评论和六榜，逐项核对分析状态、阅读/覆盖与任务恢复。009/013 连续72小时与正式指标后置。日报/周报、Obsidian、知识库检索/问答和推送是后续非核心能力，不进当前排期；真实 Codex 请求暂停。
- 单 owner 登录、主题、连接、内容、Outbox/Kafka/Worker、预算、备份、统一错误契约及 Web 工作台已有代码。宿主机单 Worker 已注册 `webpage.collect`、`keyword.search`、`source.comments`、`source.hotlist`、`analysis.annotate`、`events.cluster`、`report.daily`、`notification.send`、`knowledge.export`；独立调度进程已存在。Plan014 候选、稳定身份与 R1—R5 修复已通过受控 PostgreSQL 和远端技术门禁（EV-004-002），开关默认关闭；人工修订、热度、页面和真实三平台未验收。SMTP 待实现。
- 本人账号来源本轮仅 B 站试点。MediaCrawler 固定补丁及独立 CDP 资料记录在 `~/Desktop/Docker/mediacrawler-start-local/`，HotKey 从宿主机启动子进程；评论只读同轮缓存的一级评论每帖 ≤20 条。固定提交现为 `1bd07bc`，普通非零退出不再误归认证失效；三类版本证据、风控停用与本人确认恢复已有受控验证。修复后尚未真实采集或恢复，开关关闭；不把离线回放称为接入成功。

## 证据快照

2026-09-30 评论修复：无有效来源尾段证据、根/回复采样截断均保留部分覆盖与停止原因，重复去重不算截断。隔离 PostgreSQL/Kafka 专项 46 passed、后端全量 1062 passed/14 skipped，未发送真实来源或模型请求；范围见 Acceptance002 EV-002-051，完整核心 POC 仍待同库闭环。

2026-09-26 的可重建开发库 `hotkey_p1` 约 4 小时运行：四来源分别入库 Google News 365、SearXNG 94、HN 61、36Kr 8；六榜 59 快照，最近两小时 23 成功、1 失败；Codex 738 标注中相关字段为空 3 条。HN 45 线程来自较早且已重建的库，不可与当前库合并。四来源和六榜尚无连续 72 小时产品验收；开发库结果仅证明所述真实运行范围。B 站新建库离线回放与旧失败运行均不满足 AC-113/115/122。

## 本地运行与数据门槛

| 组件 | 入口/边界 |
|---|---|
| HotKey | 根 `docker-compose.yml`；API `127.0.0.1:8867`，Web `127.0.0.1:3000`；在 `backend/app/` 下运行 `uvicorn main:create_app --factory`、`python -m worker`、`python -m worker.scheduler` |
| RSSHub、SearXNG | 分别在 `~/Desktop/Docker/rsshub-start-local/`、`~/Desktop/Docker/searxng-start-local/` 独立 Compose；端口 `1200`、`8888` |
| Firecrawl | 独立本地编排；公开网页业务结果单独验收 |
| MediaCrawler | `~/Desktop/Docker/mediacrawler-start-local/` 保留补丁、资料和运行说明；HotKey B 站入口是宿主机子进程、`127.0.0.1` 独立 CDP 端口 |
| Codex | 本机 app-server，分析模型由 `HOTKEY_AI_MODEL` 配置，不发付费模型请求 |
| Obsidian | 现有 `~/Desktop/Markdown/Obsidian`，只写 `HotKey/`；真实写入另验 |

可丢弃开发库可按完整 `schema.sql` 新建；M1 连续运行库或正式库需保留数据时，先备份并实际验证恢复，再新建库、原子应用完整 Schema、导入并核对核心表、身份/外键、连接版本、Job/Outbox/offset、覆盖和预算，旧库保留回退。不得就地执行完整 Schema 或把开发库重建后的测试算作旧运行证据。

## 下一步

现行 Plan 为001—059。Plan059 只读预览已完成（Acceptance002 EV-002-053）：后端87、前端90项、静态/构建/生成门禁及桌面/390px通过；真实库认证端点读取20条HN样本且任务/模型/预算不变。原POC镜像未部署新端点。Plan058 A已有真实HN/百度与受控标注、Worker重启证据，评论与榜未汇齐同主题短窗；全局预算20/20后停调，下个合法窗口复跑，B待A通过。M2需本人核查，M3按014→015→016→042推进；模型、日报/知识库/推送、72小时继续后置。不得整体恢复旧stash或把准入研究当实现；新Issue从060续建。提交/推送按当前会话授权执行。
