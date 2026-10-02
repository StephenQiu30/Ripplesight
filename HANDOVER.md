# HotKey Server 交接

更新日期：2026-10-02。本文件记录实现快照（≤5 KB）；需求与合同见 [PRD001](docs/prd/001-热点舆情监控平台需求.md)、[Design001](docs/design/001-热点舆情监控平台总体设计.md)，当前执行与状态见 [Plan索引](docs/plan/README.md)、[BACKLOG](BACKLOG.md)，证据见 [文档入口](docs/README.md)。

## 当前实现与待验边界

Demo 已删除身份模块/API、密码/会话/初始化配置、登录注册页与守卫，主题工作台在 /topics，事件阅读在 /events。读无需 Cookie，写固定自定义头；业务 owner_id/created_by 是内部分区 UUID，空库固定值、单分区复用、多分区拒绝，不创建假用户或会话。来源凭据、授权、预算与幂等保留，现行合同见 Design001 §9.2。匿名技术证据见Acceptance001 EV-001-005—007；当前运行需现场核对。ToC身份留作未来需求。

保留062全量迁移及058短窗、032重试、038评论、009正式72小时、014事件候选六份计划。责任合并与删除旧卡不记功能完成。

- 058 A 未通过，B 未开始，运行基线须重新冻结；真实 Codex 暂停，72小时与正式质量后置。旧库/PID/offset/预算和切换记录见 Acceptance002 EV-002-052/056—058，不能推定当前就绪。百度 v2 真实读取、同主题联验、人工重试与实际任务恢复仍待验。
- 主题、连接、内容、Job/Outbox/Kafka/Worker、预算、备份、统一错误、阅读/覆盖及只读预览已有代码与局部证据，仍有逐来源真实缺口。时效统计的 T0 相位、真实 Codex 分母及复算未闭；旧库三条标注异常待核对，约四小时历史记录不能拼为72小时。
- 038部分覆盖受控通过（EV-002-051），逐根真实分页/尾段、旧帖新回复、重启与十帖待验。014受控通过且默认关闭；062新增事实纠错、页面与热度，真实三平台与产品条件未验。
- 通用Browser未接业务Worker，凭据换版/旧写待验，保持冻结。062补真实隔离PostgreSQL/Redis/MinIO生命周期和镜像恢复；实际业务保留库/独立灾备仍待验，日常HTTP/客户端/CI归AGENTS。

## 本人账号与来源

本人账号只限 B站研究试点。MediaCrawler 个人、非商业许可限制独立适用；固定补丁 `1bd07bc` 与独立 CDP 资料在 `~/Desktop/Docker/mediacrawler-start-local/`，HotKey 采用宿主机子进程，同轮缓存一级评论每帖≤20条。风控/停用/本人确认恢复有受控证据，修复后真实采集与恢复未过，开关关闭。验证、登录失效或频繁访问立即停用，本人核查后人工恢复。

公开热榜或Browser probe不证明其他登录平台接入；逐来源核对许可/授权/预算。X凭据及月度上限未确认前禁止真实请求。SMTP已实现默认关闭，飞书暂缓，unknown不自动重发；真实渠道核收未验。

## 本地运行与数据

| 组件 | 入口与边界 |
|---|---|
| HotKey | 根 docker-compose.yml 只启动应用；docker-compose-prod.yml 复用相同定义并显式使用 .env.prod；docker-compose-env.yml 按需启动环境，本地默认不启动。默认 API 127.0.0.1:8867、Web 127.0.0.1:3000，实际端口以配置为准。backend/app 下运行 uvicorn main:create_app --factory、python -m worker、python -m worker.scheduler。 |
| RSSHub / SearXNG | ~/Desktop/Docker 下各自 *-start-local 独立 Compose，固定端口1200/8888；主机仅127.0.0.1或host.docker.internal，重新应用预设才升连接版本。 |
| Firecrawl / MediaCrawler | 独立本地编排与资料；公开网页和平台采集分别验收，B站采用宿主机子进程及独立CDP。 |
| Codex / Obsidian | 本机 app-server，HOTKEY_AI_MODEL 显式选模型，不发付费请求；vault为~/Desktop/Markdown/Obsidian，仅写HotKey/，真实写入另验。 |

保留运行库先验证同版本备份，再新建空库、应用完整 schema.sql、导入并校验分区/外键、内容、连接版本、Job/Outbox/offset、覆盖和预算，旧库保留回退。不得对旧库执行完整 Schema；历史隔离恢复只证明其技术范围，同桶不算独立灾备。旧备份用原版本恢复，旧业务为空且仍有身份表的 Schema 拒绝 Demo 写入。

062全部模块与入口已接，包括向量/图标/选模、来源试抓与外部回执、人工修正/重跑/移链、日周月刊、公开分发、媒体与运维；最终同版本检查见Acceptance001。112表Schema只用于新空私有库，浏览器样本完整复制并对账，业务库未改。原Kafka重复/重平衡、父进程续租及MinIO中断恢复有技术证据；候选连续扫描、最终许可准入、通知原收件人和迟到费用/退出上下文已补。真实供应商/渠道/业务恢复及72小时未验，062继续in_progress；提交状态以Git为准。
