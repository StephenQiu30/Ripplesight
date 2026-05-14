## 1. 文档对齐（运行时约束）

- [x] 1.1 在 `docs/engineering/技术方案.md` 明确记录：
  - 运行默认不使用 Python 虚拟环境。
  - 不要求 Node 虚拟环境。
  - PostgreSQL 与 Redis 默认绑定本机 Homebrew 实例 `localhost`。
  - Docker Compose 仅可选，默认不创建数据库容器。
- [x] 1.2 在 `docs/plans/08-部署计划.md` 增补“非 venv / 本机 Homebrew Postgres + Redis / Docker 可选”执行边界，并与 `README` 一致。
- [x] 1.3 在 `README.md` 的本地运行章节补充上述三条约束，作为开发者验收口径。
- [x] 1.4 在 `docs/engineering/验收标准.md` 将 A7 标记为可执行且更新为指标输出范围。

## 2. 可观测指标（后端）

- [x] 2.1 在 `apps/api/app/core/middleware.py` 增加请求统计能力：
  - total requests
  - status-code buckets
  - rate-limit 429 次数
  - 活跃 rate-limit 桶数量
- [x] 2.2 新增测试工具函数以清理和获取 metrics 快照，便于红绿验证。
- [x] 2.3 新增 `apps/api/app/api/routes/ops.py`，暴露 `GET /api/ops/metrics`。
- [x] 2.4 在 `apps/api/app/main.py` 注册 ops router。
- [x] 2.5 在 `tests/test_mvp_services.py` 添加两个红绿测试：
  - metrics 包含 `total_requests`、`status_buckets`。
  - `rate_limit` 拦截情况下 `rate_limit_exceeded_total` 计数上升。

## 3. 验证与归档

- [x] 3.1 跑 `python3 -m unittest tests.test_mvp_services`（至少包含新增指标测试）。
- [x] 3.2 跑 `openspec validate --changes --json`（仅校验当前变更文件完整性）。
- [x] 3.3 根据现有规范流执行 `openspec archive --yes ops-runtime-observability-hardening`。
