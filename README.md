# Ripplesight

Ripplesight 是面向个人非商业使用的**公开资讯阅读与舆情监控项目**。围绕关键词连接来源材料、讨论与事件进展，让正在发生的变化有依据、可追溯。

GitHub 仓库：[StephenQiu30/Ripplesight](https://github.com/StephenQiu30/Ripplesight)。本机工作区为 `Ripplesight/`，当前仓库为其中的 `ripplesight-server/`，冻结的客户端为 `ripplesight-app/`。Compose 项目、容器、网络与自有镜像统一使用 `ripplesight`，生产项目为 `ripplesight-prod`。既有 `HOTKEY_*` 环境变量、数据库、历史数据卷、登录协议、MCP 工具名及 Obsidian 导出目录继续兼容现有部署；改名不迁移这些数据。

- 不登录：阅读有出处、经过去重的公开资讯、事件、日报周报，以及 AI 模型榜。
- 登录后：为关心的主题设置关键词，每小时获取各平台的热点与评论，每天看到社交媒体上最热的事件，查看情感走向，接收报告和告警。

产品目标与规划见 [PRD](workspace/content/product/prd/01-PRD.md)，每项能力现在到哪一步见[文档工作区](workspace/content/index.md)；下一步做什么，见 [BACKLOG](BACKLOG.md)。

## 快速开始

需要 Docker Compose 2.24.4+，以及已经在运行的 PostgreSQL、Redis、Kafka。如果没有，见下文「全新环境」。

```bash
cp .env.example .env
```

编辑 `.env`，填写数据库、Redis、Kafka 的连接地址和各项密钥。然后启动：

```bash
docker compose --env-file .env up --detach --build --wait backend frontend workspace
```

- 网站：<http://127.0.0.1:8666/>
- API 文档：<http://127.0.0.1:8667/docs>
- 知识库阅读：<http://127.0.0.1:8668/Ripplesight/>

前后端和知识库均由 Docker 运行，复用本机已有的数据服务。默认自动加载 `docker-compose.override.yml`，本机开启热更新：

- 修改 `backend/app/` 的 Python 代码后，API 自动重载。
- 修改 `frontend/src/` 或 `frontend/public/` 后，Next.js 开发服务器自动更新页面。
- 修改 `workspace/content/`、公开阅读清单或根目录文档后，知识库自动校验、生成页面、搜索索引和 AI 原文，然后通知已打开的页面刷新。通常需要几十秒；校验失败会在容器日志中报错并保留上一版。新增公开文档仍需登记清单并执行 `pnpm index`。

容器只读访问作者来源，依赖与生成物留在容器内。`.env`、依赖锁文件、Dockerfile 和数据库结构变化仍需按对应流程重新加载或构建。查看知识库更新结果：

```bash
docker compose logs --tail 100 workspace
```

需要重新构建依赖并重启这三个服务时：

```bash
docker compose --env-file .env up --detach --build --force-recreate --wait backend frontend workspace
```

如果 8668 仍有先前的宿主机 `pnpm preview`，先正常停止该预览进程，再启动 Compose。

本机要使用与生产一致的构建镜像时，显式选择基础文件：

```bash
docker compose --env-file .env -f docker-compose.yml up --detach --build --wait backend frontend workspace
```

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

新数据卷以当前 Compose 项目名为前缀。复用已有环境卷时，在 `.env` 中将 `HOTKEY_POSTGRES_VOLUME_NAME`、`HOTKEY_REDIS_VOLUME_NAME`、`HOTKEY_KAFKA_VOLUME_NAME` 设置为原卷名，保持现有数据存储。

## 生产

```bash
cp .env.example .env.prod
```

编辑 `.env.prod`，设置 `HOTKEY_ENVIRONMENT=production`、HTTPS 的 `HOTKEY_WEB_ORIGIN`，以及独立的生产密钥。然后启动：

```bash
docker compose --env-file .env.prod -f docker-compose-prod.yml up --detach --build --wait
```

显式选择生产文件不会加载本机热更新覆盖。API 和 Web 只绑定 localhost，需要通过反向代理对外提供访问。

停止服务时，使用与启动时相同的文件和参数执行 `down`。不要加 `--volumes`，否则会删除数据。

## 文档

文档与校验工具说明见 [workspace/README](workspace/README.md)。项目知识库用于内部开发，本机内部入口为 frontend 的 `/workspace/docs`，使用 Nextra 与 Editor.js，共用身份和样式。初始化与启动见 [本机知识库](workspace/LOCAL.md)。现有 Nextra 公开预览 <http://127.0.0.1:8668/Ripplesight/> 与公开清单继续保留；内部资料走授权 API。真实账号与 Obsidian 验收仍需完成。

| 文档 | 内容 |
|---|---|
| [PRD](workspace/content/product/prd/01-PRD.md) | 为什么做、为谁做、目标与发布规划 |
| [文档工作区](workspace/content/index.md) | 各能力的现状与验收标准（Obsidian 打开 `workspace/content`） |
| [BACKLOG](BACKLOG.md) | 优先级与进度 |
| [PROJECT](PROJECT.md) | 技术架构与约定 |
| [AGENTS](AGENTS.md) | 工程规范与检查 |
| [backend](backend/README.md) / [frontend](frontend/README.md) | 本地开发与测试 |
| [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) | 第三方代码与许可 |

参与开发见 [CONTRIBUTING](CONTRIBUTING.md)，安全问题见 [SECURITY](SECURITY.md)。本项目采用 [MIT 许可证](LICENSE)。
