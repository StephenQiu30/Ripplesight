# ai-hotspot-radar

`ai-hotspot-radar` 是一个面向内部团队的 AI 热点监测与日报平台项目骨架。

当前阶段只完成两类交付：

- 规范化项目目录
- 可直接指导后续实现的需求与市场调研文档

## 目录说明

- `docs/`：需求分析、市场调研、架构说明
- `services/api/`：`FastAPI` HTTP 服务启动与装配层
- `services/worker/`：`Celery` worker 与定时任务启动入口
- `backend/core/`：后端共享领域代码，按分层模块化组织
- `frontend/web/`：`Next.js + TypeScript` 控制台
- `contracts/openapi/`：OpenAPI 契约基线
- `infra/`：`Docker Compose`、环境变量模板与部署占位
- `scripts/`：非业务型脚本

## 当前约束

- 第一阶段不补全具体业务实现，不提前引入未经确认的依赖。
- 所有后续实现必须遵守 `docs/requirements-analysis.md` 中的工程规范与边界。
- 接口设计遵循 `OpenAPI First`，避免先写代码再反向补契约。
