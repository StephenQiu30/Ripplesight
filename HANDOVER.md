# HotKey Server 交接

更新日期：2026-10-01。本文件记录实现快照与设计变更（≤5 KB）；需求见 [PRD001 v5.2](docs/prd/001-热点舆情监控平台需求.md)，设计见 [Design001 v4.3](docs/design/001-热点舆情监控平台总体设计.md)，任务及证据见 [Plan索引](docs/plan/README.md)、[BACKLOG](BACKLOG.md) 和 [Acceptance索引](docs/README.md)。

## 账户设计与当前实现

目标是ToC多用户，保留用户名密码，与GitHub App/邮箱验证码并存；后两者首次验证可注册。删除部署密钥、单owner及独立工作区包装，保留密码哈希/恢复、会话/CSRF与资源隔离。无感登录用有效Cookie恢复；过期、撤销、退出后重新验证，不增加JWT refresh。登录邮件/报告投递分别验收。

[Plan060](docs/plan/060-GitHub与邮箱验证码登录执行计划.md) 为planned，代码仍是旧身份与用户名密码登录，GitHub/验证码尚不可用。本轮仅文档，未改代码、配置、数据库或运行环境；多用户、三种登录、无感恢复及旧库切换验收待完成，旧单用户证据不覆盖新账户AC。

## 核心边界与证据

- 核心POC按Plan058先做一个主题、HN与一榜的同库短窗A，再扩四关键词来源、HN评论和六榜B，分别核对分析状态、阅读/覆盖及恢复。A未通过、B未开始；009/013连续72小时、正式时效与质量后置。真实Codex暂停；日报/周报、Obsidian/知识库、报告导出和渠道投递后置。
- 主题、连接、内容、Outbox/Kafka/Worker、预算、备份、统一错误及Web已有代码；单宿主机Worker与独立调度已存在。Plan014 R1—R5及远端技术门禁通过，默认关闭；真实三平台、人工修订、热度和页面未验。报告SMTP待实现。
- 本人账号来源仅B站试点。MediaCrawler的个人、非商业研究许可边界独立适用，不因ToC账户设计扩大授权。固定补丁`1bd07bc`与独立CDP资料在`~/Desktop/Docker/mediacrawler-start-local/`，HotKey使用宿主机子进程，一级评论只读同轮缓存、每帖≤20条。版本/风控/停用/本人确认恢复已有受控验证；修复后真实采集和恢复未通过，开关关闭。验证、登录失效或频繁访问立即停用，须本人核查后恢复。

Plan059只读预览completed（EV-002-053/055）：桌面/390px与技术门禁通过，原POC读取20条HN/11条命中，无外采副作用。Plan001 CSP与预览来源提示修复通过；`8a7135e2` frontend90项/contract/runtime成功且已部署，配置G4/G5子项/POC-002通过，其他来源/第二用户/父级AC与058未闭。

Plan058运行见EV-002-056/057：独立工作树Worker重启快照PID50507、原组单成员offset28/lag0；收尾17:53—17:55Z现场Kafka group读取失败，当前成员未重验，不能用PID或远端runtime代替就绪。容器Worker/调度停用，百度v2真实读取待验。预算20/20，2026-10-01 08:00上海时间下窗前须恢复依赖核对单Worker，A未汇齐。

Plan038部分覆盖修复受控通过（EV-002-051），真实分页、旧帖新回复及进程重启待验。`hotkey_p1`约4小时记录与已重建库HN线程不能拼成72小时；旧标注3条异常待核对。B站离线回放不算接入成功，各证据等级分开记录。

## 本地运行与数据门槛

| 组件 | 入口与边界 |
|---|---|
| HotKey | 根docker-compose.yml；默认API 127.0.0.1:8867、Web 127.0.0.1:3000，实际端口以本地配置为准；backend/app下运行uvicorn main:create_app --factory、python -m worker、python -m worker.scheduler |
| RSSHub / SearXNG | ~/Desktop/Docker下各自*-start-local独立Compose，固定端口1200/8888；主机仅127.0.0.1或host.docker.internal，重新应用预设后升连接版本 |
| Firecrawl / MediaCrawler | 独立本地编排与资料；公开网页和平台采集分别验收，B站采用宿主机子进程及独立CDP |
| Codex / Obsidian | 本机app-server，HOTKEY_AI_MODEL选模型，不发付费请求；vault为~/Desktop/Markdown/Obsidian，仅写HotKey/，真实写入另验 |

保留运行库须先备份并实际验证恢复，再新建空库、原子应用完整schema.sql、导入并校验用户/外键、内容、连接版本、Job/Outbox/offset、覆盖与预算，旧库保留回退。不得对旧库执行完整Schema；Plan051隔离恢复技术completed，同桶不算独立灾备，最终009/013运行库需同版本重验。身份改造不得猜旧用户名对应邮箱或把旧数据交给首个新登录者。

## 下一步

现行Plan001—060，下个Issue为061；060设计planned，按三种登录、无感恢复、用户隔离与旧库合同实施。058先汇齐A再扩B；M2核查后012低频，M3按014→015→016→042推进；模型、72小时、报告/知识库/渠道待验。逐卡状态见BACKLOG/Plan；不整体恢复旧stash，文档不算实现。提交和推送依当前会话授权。
