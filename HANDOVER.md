# HotKey Server 交接

更新日期：2026-10-01。本文件记录实现快照（≤5 KB）；需求与合同见 [PRD001](docs/prd/001-热点舆情监控平台需求.md)、[Design001](docs/design/001-热点舆情监控平台总体设计.md)，当前执行与状态见 [Plan索引](docs/plan/README.md)、[BACKLOG](BACKLOG.md)，证据见 [文档入口](docs/README.md)。

## 当前实现与待验边界

Demo 已删除身份模块/API、密码/会话/初始化配置、登录注册页与守卫，直接进入 /events。读无需 Cookie，写固定自定义头；业务 owner_id/created_by 是内部分区 UUID，空库固定值、单分区复用、多分区拒绝，不创建假用户或会话。来源凭据、授权、预算与幂等保留，现行合同见 Design001 §9.2。匿名技术/浏览器证据见 Acceptance001 EV-001-005—007；当时 Web13000/API18867 使用独立 hotkey_demo_20261001 库，旧库未改，当前就绪仍须现场核对。用户名密码、GitHub App、邮箱验证码、无感登录留作未来需求。

当前只保留五份执行计划：058 先汇齐一个主题、HN与一榜的同库 A，再扩四关键词来源、HN评论和六榜 B；032 承接重试，038 承接评论，009 承接正式 M1 统计/72小时验收，014 承接事件候选。原子卡的未完成条件已合并或留在 BACKLOG，删卡不记完成。

- 058 A 未通过，B 未开始，运行基线须重新冻结；真实 Codex 暂停，72小时与正式质量后置。旧库/PID/offset/预算和切换记录见 Acceptance002 EV-002-052/056—058，不能推定当前就绪。百度 v2 真实读取、同主题联验、人工重试与实际任务恢复仍待验。
- 主题、连接、内容、Job/Outbox/Kafka/Worker、预算、备份、统一错误、阅读/覆盖及只读预览已有代码与局部证据，仍有逐来源真实缺口。时效统计的 T0 相位、真实 Codex 分母及复算未闭；旧库三条标注异常待核对，约四小时历史记录不能拼为72小时。
- 038 部分覆盖修复受控通过（EV-002-051），逐根真实分页/尾段、旧帖新回复、进程重启与十帖待验。014 受控修复通过且默认关闭，真实三平台、人工修订、热度及页面仍未验，后置能力见 Design004。
- 通用 Browser 业务处理器未接 Worker、凭据换版/旧写端到端待验，保持冻结；来源/授权/出口/预算未定不恢复。证据生命周期的引用保护、删除审计、谱系恢复和真实 MinIO 回归仍待验，日常 HTTP/客户端/CI 检查归 AGENTS。

## 本人账号与来源

本人账号只限 B站研究试点。MediaCrawler 个人、非商业许可限制独立适用；固定补丁 `1bd07bc` 与独立 CDP 资料在 `~/Desktop/Docker/mediacrawler-start-local/`，HotKey 采用宿主机子进程，同轮缓存一级评论每帖≤20条。风控/停用/本人确认恢复有受控证据，修复后真实采集与恢复未过，开关关闭。验证、登录失效或频繁访问立即停用，本人核查后人工恢复。

公开热榜或 Browser probe 不证明其他登录平台接入；逐来源分别核对许可、授权、预算与实际能力。X 凭据及月度上限未确认前禁止真实请求。日报/周报、Obsidian/知识库、导出与投递后置；报告 SMTP 待实现，飞书暂缓，未来登录邮件独立于报告渠道。

## 本地运行与数据

| 组件 | 入口与边界 |
|---|---|
| HotKey | 根 docker-compose.yml 只启动应用；docker-compose-prod.yml 复用相同定义并显式使用 .env.prod；docker-compose-env.yml 按需启动环境，本地默认不启动。默认 API 127.0.0.1:8867、Web 127.0.0.1:3000，实际端口以配置为准。backend/app 下运行 uvicorn main:create_app --factory、python -m worker、python -m worker.scheduler。 |
| RSSHub / SearXNG | ~/Desktop/Docker 下各自 *-start-local 独立 Compose，固定端口1200/8888；主机仅127.0.0.1或host.docker.internal，重新应用预设才升连接版本。 |
| Firecrawl / MediaCrawler | 独立本地编排与资料；公开网页和平台采集分别验收，B站采用宿主机子进程及独立CDP。 |
| Codex / Obsidian | 本机 app-server，HOTKEY_AI_MODEL 显式选模型，不发付费请求；vault为~/Desktop/Markdown/Obsidian，仅写HotKey/，真实写入另验。 |

保留运行库先验证同版本备份，再新建空库、应用完整 schema.sql、导入并校验分区/外键、内容、连接版本、Job/Outbox/offset、覆盖和预算，旧库保留回退。不得对旧库执行完整 Schema；历史隔离恢复只证明其技术范围，同桶不算独立灾备。旧备份用原版本恢复，旧业务为空且仍有身份表的 Schema 拒绝 Demo 写入。

下一步按058重新冻结并完成A→B；其余后置工作按需求/设计和BACKLOG排期时再补必要步骤，不整体恢复旧stash。提交推送依会话授权。
