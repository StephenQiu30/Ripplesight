# 运行时与可观测性硬化（低耦合补强）

本变更聚焦两项低耦合 P0 任务：

1. 明确运行时约束与部署文档收口，确保“无虚拟环境、连接本机 Homebrew PostgreSQL/Redis、Docker 可选”在技术方案、部署计划、README 中一致。
2. 增补运行时可观测指标端点与测试，支撑 `A7` 可观测验收（抓取、AI、邮件、任务指标可追踪）。

目标为可直接驱动本地计划执行，不引入企业级重构和额外队列平台。

## Why

- 运行时约束长期分散，导致开发者在部署前对 venv、PostgreSQL/Redis 来源和 Docker 边界理解不一致。
- 可观测面缺少一类最小运行时入口，影响问题定位效率与验收闭环。

## What Changes

- 明确更新 `README`、`docs/engineering/技术方案.md`、`docs/plans/08-部署计划.md`、`docs/engineering/验收标准.md` 的运行时与部署边界。
- 新增 `GET /api/ops/metrics` 与对应中间件级指标采集（请求总数、状态码分桶、429 次数、活跃限流客户端数）。
- 在 `tests/test_mvp_services.py` 添加指标 API 与限流计数的红绿测试，更新并归档。
