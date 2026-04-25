# ai-hotspot-radar

`ai-hotspot-radar` 是一个面向内部团队的 AI 热点监测与日报平台 MVP。

项目采用分层架构（`FastAPI + Celery + 共享领域层`）进行搭建，围绕“监听 AI 热点 -> 形成可验证事件 -> 生成日报 -> 邮件闭环”打通全链路。

当前已完成：阶段 1~4 文档冻结与实现闭环（日报生成、中文摘要、证据链接、邮件状态追踪），并完成 Stage 5 控制台基础读链路（列表/详情/搜索/反馈/配置）。

## 目录说明

- `backend/core/`：领域/应用服务层（分层设计，供 API 与 Worker 共用）
- `services/api/`：`FastAPI` 服务与路由、依赖、序列化
- `services/worker/`：`Celery` worker 与定时任务入口
- `contracts/`：OpenAPI 契约基线
- `docs/`：产品、计划、技术、验收与市场文档（主事实源）
- `infra/`：部署相关配置（`docker-compose` 等）
- `scripts/`：日常脚本

## 文档入口（主事实源）

文档体系采用“主入口 + 分拆子文件”的方式，优先以这些文件为准：

- [产品需求（PRD）总入口](./docs/product/prd.md)
  - `docs/product/prd/01-goals-and-positioning.md`
  - `docs/product/prd/02-scope-and-non-scope.md`
  - `docs/product/prd/03-features-by-phase-p0-p1.md`
  - `docs/product/prd/04-success-metrics.md`
  - `docs/product/prd/05-risks-and-assumptions.md`
- [项目计划](./docs/product/plan.md)
- [技术方案](./docs/engineering/tech-spec.md)
- [验收标准](./docs/engineering/acceptance.md)
- [文档导航](./docs/README.md)

`docs/requirements-analysis.md` 保持归档性质，不再作为主事实源继续扩展。

## 开发与验证

### 环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 一键启动（推荐）

在仓库根目录直接执行：

```bash
cp infra/env/.env.example infra/env/.env
docker compose --profile app up -d --build
```

- 核心入口：`http://127.0.0.1:3000`
- API 访问：`curl -fsS http://127.0.0.1:8000/api/events?page=1&page_size=1`

### 全量服务（可选）

同样在仓库根目录执行：

```bash
cp infra/env/.env.example infra/env/.env
docker compose --profile app --profile jobs up -d --build
```

- 包含 `worker`、`beat`、`redis`、`postgres`，用于异步任务链路/后台调度验证。
- 全量启动后如只验证主链路，可使用 `docker compose --profile app up -d --build` 启动。

### 本地运行建议

```bash
cd frontend/web
npm install
npm run api:gen
npm run dev
```

- API 服务：运行 `services/api/app.py` 对应的 FastAPI 应用（按项目启动脚本或 `uvicorn` 方式）
- Worker：运行 `services/worker/app.py` 与 `services/worker/tasks.py` 入口的 Celery 配置

### 测试与验收

- 单元测试：

```bash
.venv/bin/python -m unittest discover -s tests
```

- OpenSpec 校验：

```bash
openspec validate --json
openspec validate --specs --json
```

## 实施状态

- 阶段 1：文档体系与范围冻结 ✅
- 阶段 2：来源采集与标准化打通 ✅
- 阶段 3：事件聚合与评分闭环 ✅
- 阶段 4：日报生成与邮件闭环 ✅（中文摘要/证据链路 + 降级发送 + 交付状态）
- 阶段 5：控制台/搜索闭环（可运行，`frontend/web` 已接入 `@umijs/openapi`）

## 开发约束

- 所有实现变更应先能追溯到 PRD 对应条目和 Acceptance 阶段项。
- OpenAPI 为契约基线，新增/变更字段需联动更新文档与验收。
- 避免一次性重构，优先“可运行 + 可回滚”的小步迭代。
