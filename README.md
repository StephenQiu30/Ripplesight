# HotKey · 知微见澜

HotKey 是一个**公开资讯阅读站 + 个人舆情监控**工具，个人非商业使用。

- 不登录：阅读有出处、经过去重的公开资讯、事件、日报周报，以及 AI 模型榜。
- 登录后：为关心的主题设置关键词，每小时获取各平台的热点与评论，每天看到社交媒体上最热的事件，查看情感走向，接收报告和告警。

每项能力现在到哪一步，见 [产品总览](docs/README.md)；下一步做什么，见 [BACKLOG](BACKLOG.md)。

## 快速开始

需要 Docker Compose 2.20+，以及已经在运行的 PostgreSQL、Redis、Kafka。如果没有，见下文「全新环境」。

```bash
cp .env.example .env
```

编辑 `.env`，填写数据库、Redis、Kafka 的连接地址和各项密钥。然后启动：

```bash
docker compose --env-file .env up --detach --build --wait
```

- 网站：<http://127.0.0.1:8666/>
- API 文档：<http://127.0.0.1:8667/docs>

启动后台任务。Worker 建议跑在宿主机上，见 [backend/README](backend/README.md)；Scheduler 可以用 Compose 启动：

```bash
docker compose --env-file .env --profile worker up --detach scheduler
```

## 全新环境

只有在没有可复用的 PostgreSQL、Redis、Kafka 时才执行：

```bash
docker compose --env-file .env -f docker-compose-env.yml up --detach --wait
```

它只会在全新的空数据卷上初始化 `backend/database/schema.sql`。不要在已有业务库上执行这个脚本，升级方法见 [PROJECT §6](PROJECT.md#6-数据库)。

## 生产

```bash
cp .env.example .env.prod
```

编辑 `.env.prod`，设置 `HOTKEY_ENVIRONMENT=production`、HTTPS 的 `HOTKEY_WEB_ORIGIN`，以及独立的生产密钥。然后启动：

```bash
docker compose --env-file .env.prod -f docker-compose-prod.yml up --detach --build --wait
```

API 和 Web 只绑定 localhost，需要通过反向代理对外提供访问。

停止服务时，使用与启动时相同的文件和参数执行 `down`。不要加 `--volumes`，否则会删除数据。

## 文档

| 文档 | 内容 |
|---|---|
| [docs](docs/README.md) | 产品定位、能力、现状与验收标准 |
| [BACKLOG](BACKLOG.md) | 优先级与进度 |
| [PROJECT](PROJECT.md) | 技术架构与约定 |
| [AGENTS](AGENTS.md) | 工程规范与检查 |
| [backend](backend/README.md) / [frontend](frontend/README.md) | 本地开发与测试 |
| [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) | 第三方代码与许可 |

参与开发见 [CONTRIBUTING](CONTRIBUTING.md)，安全问题见 [SECURITY](SECURITY.md)。本项目采用 [MIT 许可证](LICENSE)。
