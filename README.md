# HotKey · 知微见澜

从一个关键词观察变化：收集公开或获授权的内容，追踪主题与来源，并逐步生成可追溯的舆情日报、周报和本地知识库。

HotKey 面向关注 AI 等专业方向的用户，是 ToC 信息监控产品；代码授权范围以 [MIT 许可证](LICENSE) 为准，来源组件及数据的许可需要分别核对。本仓库包含 Python 后端和 Next.js Web 前端；独立的 [Flutter 客户端仓库](https://github.com/StephenQiu30/hotkey-app) 目前尚未初始化。项目仍在开发中，适合试用和参与开发，完整产品验收尚未完成。

## 当前能做什么

- Web 已有监控主题、关键词规则和来源连接管理页面；账户实现的替换状态见下方说明。
- 使用 PostgreSQL 保存内容、任务与运行状态；Kafka Worker 执行持久任务，Web 展示主题、来源、内容、任务和报告页面。
- 已有 Hacker News、RSS、网页搜索等采集适配器及调度、分析、日报相关代码；实际来源需要单独配置和验证。
- 提供 FastAPI 自动生成的 OpenAPI、Swagger UI 与 Scalar 文档。

**当前边界：**项目正在验证真实来源采集、评论、模型标注和日报链路。邮件推送、周报、事件归并、知识库后续能力及连续运行验收尚未完成；页面、适配器、单元测试或服务健康检查不代表某来源已经通过真实业务验收。最新进度和验收状态以 [BACKLOG](BACKLOG.md) 为准。

## Demo 访问

当前 Demo 直接打开 `/events`，无需登录、注册、部署密钥或账户初始化。登录页面、身份 API、会话守卫和密码依赖随 [Plan061](docs/plan/061-Demo用户体系与历史依赖清理执行计划.md) 删除。

Demo 用于本机或受控演示环境，写请求使用固定 `X-HotKey-CSRF: 1` 自定义头；前端自动设置。内部历史分区 UUID 只维持业务数据关联。已有运行库不清空、不就地应用新 Schema。

未来 ToC 的用户名密码、GitHub App、邮箱验证码和无感登录需求后置，实施前重新设计和验收；当前访问与数据合同见 [Design 001 §9.2](docs/design/001-热点舆情监控平台总体设计.md)。

## 快速启动本地底座

需要 Docker 与 Docker Compose。以下命令在本仓库根目录执行，会创建本地 PostgreSQL、Redis、Kafka、API 和 Web 容器；首次启动需要构建镜像。请先在**本地未跟踪**的 `.env` 中设置 URL 安全的随机数据库密码。不要提交 `.env` 或把凭据粘贴到 Issue。

```bash
cp .env.example .env
# 编辑 .env，设置 HOTKEY_POSTGRES_PASSWORD
docker compose config --quiet
docker compose build
docker compose up --detach --wait
```

启动后可打开 [业务页面](http://127.0.0.1:3000/events)，通过以下接口核对 API 底座。API 默认位于 `127.0.0.1:8867`，接口文档位于 `/docs` 和 `/scalar`；端口可在本地 `.env` 中调整。使用当前完整 Schema 的空库验证 Demo，保留运行库需遵守备份、导入与回退要求。

```bash
curl --fail http://127.0.0.1:8867/api/health
curl --fail http://127.0.0.1:8867/api/ready
```

Worker 是按需 profile，可在底座启动后运行：

```bash
docker compose --profile worker up --detach worker
```

这套 Compose 启动步骤只验证本地底座。RSSHub/SearXNG 由宿主机独立运行；Compose Worker 的 `HOTKEY_RSSHUB_HOST/HOTKEY_SEARXNG_HOST` 默认 `host.docker.internal`，分别访问固定 1200/8888 端口，宿主机 Worker 使用 `127.0.0.1`。预设只接受这两个主机、固定路由与 SearXNG 的 `duckduckgo news` 引擎；主机选择写入连接版本，已有连接需重新应用预设后生效。周期调度与实际采集还需要按来源配置外部服务、准入与预算，并完成对应的真实验收；现有 Compose 没有独立调度服务。不要对已有业务数据库直接执行 `backend/database/schema.sql`，它仅用于**全新空库**。停止服务请用 `docker compose down`；不要随意添加 `--volumes`，这会删除本地数据卷。更详细的开发与运行说明见 [后端 README](backend/README.md) 和 [Web README](frontend/README.md)。

## 技术与文档

后端使用 Python 3.12、FastAPI、SQLAlchemy 2、PostgreSQL、Redis 和 Kafka；Web 使用 Next.js、React、TypeScript 与 pnpm。`backend/database/schema.sql` 是数据库结构事实源；API 契约由运行中的 FastAPI 生成，再生成 Web 客户端。

| 文档 | 用途 |
| --- | --- |
| [项目约束](PROJECT.md) | 架构、目录与运行边界 |
| [文档索引](docs/README.md) | 需求、设计、计划与验收记录 |
| [进度看板](BACKLOG.md) | 当前任务和真实验收状态 |
| [贡献指南](CONTRIBUTING.md) | 开发、验证与 PR 要求 |
| [安全策略](SECURITY.md) | 私密报告漏洞及敏感信息处理 |

仅采集公开或获授权的数据；请遵守来源平台规则与适用法律，并自行控制请求频率、凭据与数据保留。MediaCrawler 的许可与个人、非商业研究边界独立适用；当前只保留本人账号 B 站低频试点，不能因 ToC 账户设计扩大其使用范围或视作其他用户、商业场景及来源平台的授权。

## 参与项目

欢迎提交问题、文档修正与聚焦的 Pull Request。开始前请阅读 [贡献指南](CONTRIBUTING.md) 和 [进度看板](BACKLOG.md)；涉及来源接入时请说明真实可用的能力、失败状态和验证范围。安全漏洞请按 [安全策略](SECURITY.md) 私密报告。

本项目采用 [MIT 许可证](LICENSE)。
