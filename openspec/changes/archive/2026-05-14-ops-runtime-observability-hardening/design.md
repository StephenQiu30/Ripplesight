# Design

## 1. 约束对齐（文档层）

- 保持单一 MVP 运行假设：Python/Node 以系统运行环境启动，不强制创建虚拟环境。
- PostgreSQL/Redis 按本机 Homebrew 实例（`localhost`）为默认运行边界。
- Docker 仅作为可选启动路径，不用于“默认新建数据库”模式。

## 2. 可观测性扩展（后端）

- 在现有 `apps/api/app/core/middleware.py` 增加内存级请求指标采集：
  - 总请求数
  - 按状态码计数
  - 429 限流次数
  - 活跃 rate limit 桶数量
- 新增 `GET /api/ops/metrics` 只读路由，读取指标快照并返回，保持无状态（服务重启即清空）。
- 与现有 rate-limit 中间件低耦合：只读调用其统计快照，不改变限流判定逻辑。

## 3. 验收闭环

- 更新 `docs/engineering/验收标准.md` 的 A7 条目为可验证状态并在 `docs/plans/08-部署计划.md` 与 `docs/engineering/技术方案.md` 标注运行时边界。
