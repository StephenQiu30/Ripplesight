# ai-hotspot-radar

`ai-hotspot-radar` 是一个可自部署的 AI 热点监控工具 MVP。

当前项目从零重建：旧实现、旧目录结构、旧数据库结构、旧 OpenAPI 契约和旧示例数据均不保留。后续实现以 `docs/plans/` 下的执行计划为准。

## 技术栈

- 前端：`Next.js + TypeScript`
- 后端：`Python + FastAPI`
- 数据库：`PostgreSQL`
- ORM：`SQLAlchemy 2.0`
- Schema 管理：`sql/*.sql` + `SQLAlchemy 2.0` models（无迁移）
- 邮件：`SMTP`
- AI：OpenAI 兼容模型 API
- 部署：本机 PostgreSQL + 本地进程；Docker Compose 仅作为可选的 API/Web 容器启动方式

## 新目录说明

- `apps/api/`：FastAPI 后端（含 SQLAlchemy models 与初始化入口）
- `apps/web/`：Next.js 控制台
- `packages/core/`：轻量共享常量、类型或规则说明
- `sql/`：PostgreSQL 表结构 SQL，当前以 `001_init_schema.sql` 为事实源
- `infra/`：环境变量、Docker 可选配置和部署配置
- `docs/plans/`：拆分后的执行计划
- `docs/product/`：PRD 与产品事实源
- `docs/engineering/`：技术方案与验收标准

## 文档入口

- [协作规范](./AGENTS.md)
- [文档导航](./docs/README.md)
- [产品需求](./docs/product/prd.md)
- [执行计划导航](./docs/product/plan.md)
- [技术方案](./docs/engineering/tech-spec.md)
- [验收标准](./docs/engineering/acceptance.md)
- [执行计划](./docs/plans/00-foundation-plan.md)

## 本地开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
npm --prefix apps/web install
```

启动 API：

```bash
npm run api:dev
```

启动 Web：

```bash
npm run web:dev
```

数据库连接：

```bash
cp infra/env/.env.example infra/env/.env
```

然后把 `infra/env/.env` 中的 `DATABASE_URL` 改成你本机 PostgreSQL 的连接串，例如：

```bash
DATABASE_URL=postgresql+psycopg://你的用户:你的密码@localhost:5432/ai_hotspot_radar
```

本机 PostgreSQL 可以使用你已经创建的 `root` 角色；真实密码只写入本地 `infra/env/.env`，不要提交到 GitHub。

数据库初始化：

```bash
npm run db:init
```

如果需要重置数据库，直接在本机 PostgreSQL 中删除并重建 `ai_hotspot_radar` 数据库，再执行：

```bash
npm run db:init
```

可选 Docker 启动 API/Web：

```bash
npm run docker:up
```

数据库表结构：

- 表结构事实源位于 `sql/001_init_schema.sql`。
- API 启动时会执行该 SQL 文件初始化本机 PostgreSQL 中的空数据库。
- SQLAlchemy models 只负责运行时访问数据库，必须与 SQL 文件保持一致。

## 后端能力

- 热点检查：`POST /api/check-runs`
- 热点列表：`GET /api/hotspots`
- 单条热点邮件通知：SMTP 配置存在时自动发送
- AI 日报生成：`POST /api/daily-reports`
- AI 日报发送：`POST /api/daily-reports/{report_id}/send`
- AI 日报列表：`GET /api/daily-reports`

AI 日报默认不自动发送；如需简单定时发送昨日日报，可在本地 `.env` 中开启：

```bash
DAILY_DIGEST_ENABLED=true
DAILY_DIGEST_HOUR=8
```

## 当前状态

- 已移除旧实现结构。
- 已建立新项目骨架。
- 已写入 `docs/plans/` 执行计划。
- 后端与控制台 MVP 已按 OpenSpec 计划推进，后续继续按计划文件小步完善。
