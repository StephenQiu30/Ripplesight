---
layer: PRD
doc_no: "10"
audience:
  - PM
  - Dev
  - Ops
feature_area: backend-operability
purpose: "定义 API/Web/Nginx 统一部署链路的最小可达要求与健康验证规则。"
canonical_path: "docs/product/prd/10-部署链路与健康可达PRD.md"
status: draft
version: "0.1.0"
owner: "StephenQiu30"
inputs:
  - "docker-compose.prod.yml"
  - "Dockerfile.api"
  - "Dockerfile.web"
  - "docs/engineering/验收标准.md"
outputs:
  - "可复用的部署可达性验收清单"
  - "故障恢复与回滚动作清单"
triggers:
  - "企业级 P0 启动并要求上线验证"
  - "生产链路可达性无法稳定复现"
downstream:
  - "docs/plans/18-部署链路与健康可达计划.md"
  - "docs/enterprise-p0-backlog-gap-review.md"
---

# 部署链路与健康可达 PRD（B2）

## 1. 背景

企业级 P0 仍缺“从 compose 启动到 API/Web 真实可达”的闭环证据。
本 PRD 要求把部署验证固定为可复用流程，避免环境配置和启动顺序差异导致的线上风险。

## 2. 目标

- 形成 API/Web/Nginx 的最小可运行链路：`docker compose up -d` 后，
  `api`、`web`、`postgres`、`redis` 均可稳定启动；
- 明确可达性检查标准：至少包含 `/api/health`、前端入口（`/`、`/app`）与任务触发可达；
- 完成重启、回滚、重建场景的恢复步骤记录。

## 3. 非目标

- 不新增复杂蓝绿发布和多副本编排；
- 不要求零停机部署；
- 不要求覆盖 Kubernetes 等高级编排形态。

## 4. 功能定义

- 启动链路
  - 验证 `web` 依赖 `api` 健康、`api` 依赖 `postgres/redis` 健康。

- 可达性门禁
  - API：`GET /api/health` 返回 200。
  - 应用：`http://localhost:3000/` 可返回页面 HTML，`/app` 可返回工作台。
  - 任务：可在后台触发一次即时检查并在 `check_runs` 有记录。

- 运维动作
  - 记录重建镜像/重启服务/回滚镜像的标准指令。

## 5. 验收场景

- 场景 1：首次启动
  - Given 一份干净环境变量
  - When 执行 compose 启动
  - Then 四类服务进入 healthy/启动成功状态

- 场景 2：重启恢复
  - Given 其中任一服务异常重启
  - When 执行 `docker compose restart`
  - Then 30 分钟内恢复到可达状态并有日志记录

- 场景 3：回滚演练
  - Given 镜像标签回退
  - When 重新部署
  - Then API/Web 可再次可达并有恢复时间记录

## 6. 风险与边界

- 数据库端口冲突、Nginx 端口映射错误；
- 环境变量污染导致服务启动成功但功能不可用；
- 镜像构建缓存导致部署行为不可复现。

## 7. 交付与验收

- `docs/plans/18-部署链路与健康可达计划.md` 可执行。
- 每次部署回放需附带 compose 输出和至少三项健康检查截图或日志。
- 将结果回填至 `docs/验收差距清单.md` 的“需真实配置后验收”。

## 8. 变更记录

| 日期 | 作者 | 版本 | 变更说明 |
| --- | --- | --- | --- |
| 2026-05-24 | StephenQiu30 | 0.1.0 | 新建 B2 部署链路 PRD |
