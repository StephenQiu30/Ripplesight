# HotKey Server 交接

更新日期：2026-10-02。实现合同见 [PROJECT](PROJECT.md)、[Design001](docs/design/001-热点舆情监控平台总体设计.md) 和 [Design048](docs/design/048-AIHOT全量迁移架构与兼容设计.md)；任务状态只见 [BACKLOG](BACKLOG.md)，证据见 [Acceptance](docs/README.md)。

## 当前实现

Python/FastAPI、Next.js、PostgreSQL、Redis、Kafka 和 MinIO 承载主题、来源、内容/评论、分析、事实/事件、热度、日周月刊、公开投影与分发、模型榜、Codex 公告、通知、知识库和运营维护。API、Worker、CLI、调度和页面使用同一领域合同、Job/Outbox 及调用/预算账本；没有第二套后端或队列。

Demo 不建立登录、注册、账户或会话。业务读取无需 Cookie，写入使用固定 `X-HotKey-CSRF: 1`；owner_id/created_by 仅为内部分区 UUID。空库使用固定分区、单分区复用、多分区拒绝；运营令牌和来源凭据分别管理。

HN 新任务要求连接配置匹配当前完整预设；缺少 comment_scan 的配置须显式重新应用预设并产生新版本。已受理任务继续使用其冻结版本，不据当前配置改写历史任务。

## 本地运行

业务库统一为 `hotkey`，112 表结构来自完整 schema.sql。本机 API 为 `127.0.0.1:8867`，Web 当前为 `127.0.0.1:3001`；Swagger `/docs`、Scalar `/scalar`、契约 `/openapi.json`。本机 backend/.env 与根 Compose .env 均已指向同一业务库，密钥不入 Git。API 和 Web 已启动；Worker/调度按需单独启动。

根 docker-compose.yml 只编排应用，生产文件复用相同定义并显式使用 .env.prod；docker-compose-env.yml 仅在需要独立基础环境时使用。PostgreSQL/Redis/Kafka、MinIO、Firecrawl、RSSHub/SearXNG 复用既有服务；本次未删除其他项目数据库或持久卷。

临时测试、旧 Demo 和空旧库已经按用户授权清理；旧 Demo 的配置数据先做了 PostgreSQL custom-format 备份和实际恢复核对。业务库使用本次运行的完整 Schema，未导入旧 Demo 配置。集成测试只在独立 hotkey_test_<suffix> 库执行，并在结束后删除；恢复临时库由所属恢复流程清理。保留数据升级先验证备份，在新空库应用完整 Schema 后导入校验，不对旧业务库直接执行 DDL。

## 剩余验证与启用条件

Plan062 只保留真实验证与缺陷修复；058 短窗 A 未通过、B 未开始，032 人工重试、038 真实 HN 分页/旧帖新回复、009 同窗 72 小时与保留库恢复、014 真实归并条件继续保留。受控技术、真实来源/供应商和产品验收分别判断。原主题周报与扫描解耦、知识库问答、质量统计与独立灾备的缺口见 BACKLOG 及所属 PRD。

真实 Codex 和付费调用仍暂停；来源准入、版本化预设、许可和预算上限保持有效。X 凭据/月度上限未确认前禁止真实请求；SMTP 默认关闭，飞书暂缓，发送 unknown 只允许人工确认。公开分发逐次复验所有成员许可、人工版本和撤回状态。

B 站仅限本人账号、个人非商业研究的 MediaCrawler 宿主机试点；固定补丁与独立 CDP 资料在 ~/Desktop/Docker/mediacrawler-start-local/。同轮一级评论每帖最多 20 条；遇验证、失效或频繁访问立即停用，本人核查后恢复。开关关闭，真实修复采集与恢复尚未通过。通用 Browser 保持冻结，probe 不代表业务平台接入。

已承接的源码调研和移植过程从 Git 查询，固定上游版本与完整许可证保留在 THIRD_PARTY_NOTICES.md。文档清理不关闭真实验收缺口。
