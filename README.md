# ai-hotspot-radar

`ai-hotspot-radar` 是一个可自部署的 AI 热点监控工具 MVP。

当前项目从零重建：旧实现、旧目录结构、旧数据库结构、旧 OpenAPI 契约和旧示例数据均不保留。后续实现以 `docs/plans/` 下的执行计划为准。

## 技术栈

- 前端：`Next.js + TypeScript`
- 后端：`Python + FastAPI`
- 数据库：`PostgreSQL`
- ORM：`SQLAlchemy 2.0`
- Schema 管理：`SQLAlchemy create_all` + 直接重建数据库（无迁移）
- 邮件：`SMTP`
- AI：OpenAI 兼容模型 API
- 部署：`Docker Compose`

## 新目录说明

- `apps/api/`：FastAPI 后端（含数据库模型与初始化/重建入口）
- `apps/web/`：Next.js 控制台
- `packages/core/`：轻量共享常量、类型或规则说明
- `infra/`：Docker、环境变量和部署配置
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

Docker 启动：

```bash
cp infra/env/.env.example infra/env/.env
npm run docker:up
```

数据库重置（删除历史内容后重建）：

```bash
npm run db:reset
```

## 当前状态

- 已移除旧实现结构。
- 已建立新项目骨架。
- 已写入 `docs/plans/` 执行计划。
- 尚未实现完整业务闭环；后续按计划文件逐步实现。
