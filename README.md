# HotKey · 知微见澜

从一个关键词观察变化：收集公开或获授权的内容，追踪主题与来源，并逐步生成可追溯的舆情日报、周报和本地知识库。

HotKey 面向关注 AI 等专业方向的用户，是 ToC 信息监控产品；代码授权范围以 [MIT 许可证](LICENSE) 为准，来源组件及数据的许可需要分别核对。本仓库包含 Python 后端和 Next.js Web 前端；独立的 [Flutter 客户端仓库](https://github.com/StephenQiu30/hotkey-app) 目前尚未初始化。项目仍在开发中，适合试用和参与开发，完整产品验收尚未完成。

## 当前能做什么

- Web 提供主题、来源、内容搜索、事件阅读、热榜、报告、模型榜、公告及独立运营页面，当前 Demo 无需登录。
- 使用 PostgreSQL 保存内容、任务与运行状态；Kafka Worker 执行持久任务，Web 展示主题、来源、内容、任务和报告页面。
- 已接入 Hacker News、RSS、网页搜索和编辑来源适配器，以及分析、事件、日周月刊、公开分发和通知任务；实际来源、模型和渠道需要单独配置和验证。
- 提供 FastAPI 自动生成的 OpenAPI、Swagger UI 与 Scalar 文档。

**当前边界：**真实来源、模型质量、事件归并、报告、渠道、保留库恢复及连续运行验收仍有缺口。功能代码、单元测试或服务健康检查不代表真实业务通过，最新状态见 [BACKLOG](BACKLOG.md)。

## Demo 访问

当前 Demo 直接打开 `/events`，无需登录、注册、部署密钥或账户初始化。访问和历史分区合同见 [Design001 §9.2](docs/design/001-热点舆情监控平台总体设计.md#92-当前-demo-的访问与数据分区)。

Demo 用于本机或受控演示环境，写请求使用固定 `X-HotKey-CSRF: 1` 自定义头；前端自动设置。内部历史分区 UUID 只维持业务数据关联。已有运行库不清空、不就地应用新 Schema。

未来 ToC 的用户名密码、GitHub App、邮箱验证码和无感登录需求后置，实施前重新设计和验收；当前访问与数据合同见 [Design 001 §9.2](docs/design/001-热点舆情监控平台总体设计.md)。

## 启动服务

需要 Docker Compose 2.20.0 或更新版本。三份编排的职责如下：

| 文件 | 职责 |
| --- | --- |
| `docker-compose.yml` | 启动 API/Web；Worker、Browser/出口代理、CLI 保留按需 profile |
| `docker-compose-env.yml` | 单独启动 PostgreSQL/Redis/Kafka，本地开发默认不启动 |
| `docker-compose-prod.yml` | 通过 include 复用全部应用定义，以独立密钥启动生产服务 |

本地开发复用已运行的环境，业务数据库名固定为 `hotkey`。首次使用复制模板；已有 `.env` 只补齐连接项，不覆盖现有密钥。配置完整 `HOTKEY_DATABASE_URL`、`HOTKEY_REDIS_URL` 和 `HOTKEY_KAFKA_BOOTSTRAP_SERVERS`，容器访问宿主机使用 `host.docker.internal`。Kafka 的 advertised listeners 也必须能从应用容器访问。

```bash
cp .env.example .env
# 编辑 .env：设置已有环境的连接地址与密钥
docker compose --env-file .env config --quiet
docker compose --env-file .env up --detach --build --wait
```

启动后打开 [业务页面](http://127.0.0.1:3000/events)，API 默认位于 `127.0.0.1:8867`，接口文档位于 `/docs` 和 `/scalar`。开发与生产的服务、镜像、命令、profile、端口规则、资源和安全限制相同，生产入口仅复用定义并使用独立项目名；连接信息与密钥由各自环境文件注入。

```bash
cp .env.example .env.prod
# 编辑 .env.prod：设置生产连接信息与独立密钥
docker compose --env-file .env.prod -f docker-compose-prod.yml config --quiet
docker compose --env-file .env.prod -f docker-compose-prod.yml up --detach --build --wait
```

生产命令始终显式指定 `--env-file .env.prod`，避免默认加载本地 `.env`。API/Web 在两种环境均只绑定 localhost，由已有反向代理接入。两份应用 Compose 都不会创建数据库、缓存或 Kafka。

仅在没有可复用环境、确实需要全新基础设施时，才运行环境文件：

```bash
docker compose --env-file .env -f docker-compose-env.yml up --detach --wait
```

环境编排保留原 `hotkey` 项目名与三个持久卷名，只在全新 PostgreSQL 空卷初始化完整 Schema；宿主机端口默认为 PG `5432`、Redis `6379`、Kafka `19092`。已有端口占用时继续复用现有服务。若应用也使用该环境，可将 `.env` 的数据库 URL 指向 `postgres:5432/hotkey`（密码与 `HOTKEY_POSTGRES_PASSWORD` 一致），Redis 指向 `redis:6379/0`、Kafka 指向 `kafka:9092`，并用同一个组合命令管理其生命周期：

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose-env.yml up --detach --build --wait
```

Worker 保留按需 profile；当前 P1 仍使用宿主机 Worker，避免并行消费者争抢消息。需要容器 Worker 的受控环境可执行 `docker compose --env-file .env --profile worker up --detach worker`；生产命令同样加上 `--env-file .env.prod -f docker-compose-prod.yml`。CLI 使用 `docker compose --env-file .env run --rm cli`，Browser 使用 `--profile browser`，其授权与出口门槛保持有效。

RSSHub/SearXNG、Firecrawl、MinIO 和 MediaCrawler 继续使用既有独立环境；RSSHub/SearXNG 的 Compose 主机默认 `host.docker.internal`，固定端口为 1200/8888。现有 Compose 没有独立调度服务。上述启动与健康检查只验证运行底座，真实来源、模型与产品闭环仍需单独验收。不要对已有业务库执行 `backend/database/schema.sql`。停止时使用与启动相同的文件、环境和项目参数执行 `down`，不要添加 `--volumes` 或 `--remove-orphans`；分开启动的应用与环境共用默认网络时，全部停止后再移除网络。详细说明见 [后端 README](backend/README.md) 和 [Web README](frontend/README.md)。

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
