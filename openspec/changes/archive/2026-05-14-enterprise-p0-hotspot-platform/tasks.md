---
change_name: enterprise-p0-hotspot-platform
version: "1.1.0"
status: draft
owner: "AI Architect"
---

# Enterprise P0 Task Plan (low coupling)

## 0. 执行原则

- 任务主事实源：`docs/product/产品需求文档.md`、`docs/engineering/技术方案.md`、`docs/engineering/验收标准.md`、`docs/product/执行计划导航.md`。
- 不可一次性重构横切功能；以“最小边界模块”实现后再组合。
- 每项任务必须有测试闭环（至少一条可执行单元/集成测试）。
- 任务之间优先串成“依赖链 + 并行链”，减少耦合。

## 1. P0 低耦合任务清单（企业级补齐版）

- [x] E1. 初始化企业级技术基线（依赖：无）
  - 产出：`infra/env/.env.example` 补全（数据库、AI provider、SMTP、RSS token、调度开关），`docs/engineering/验收标准.md` 可追踪项。
  - 验收：启动时仅依赖环境变量；缺省安全退化不阻塞可运行闭环。
  - 测试：环境变量加载测试（含默认值、空值覆盖）。

- [x] E2. Repository 与模型边界对齐（依赖：E1）
  - 产出：`sql/001_init_schema.sql` 与 `apps/api/app/models` 已对齐的仓储接口（keywords/sources/hotspots/ai_analyses/reports/check_runs/notifications/settings）。
  - 验收：表主键、外键、约束、JSONB 字段与检索字段可通过建表+插入基础查询验证。
  - 测试：建库 smoke test + 简单增删改查测试。

- [x] E3. Provider 核心框架（依赖：E2）
  - 产出：`BaseProvider`、`provider registry`、`provider factory`，并保留失败隔离接口。
  - 验收：同一 `source_type` 可解析为实例；未注册源返回清晰错误但不阻塞主流程。
  - 测试：Provider 注册/解析测试、未注册异常测试。

- [x] E3.1 扩展两类来源接入（依赖：E3）
  - 产出：RSS 与 Hacker News/GitHub Trending 中任一条来源接入完成并有可观测失败重试路径。
  - 验收：来源失败记录到任务日志，不中断全量抓取。
  - 测试：mock provider 成功 + 失败用例。

- [x] E4. AI Provider 抽象与 provider 切换（依赖：E2）
  - 产出：`BaseLLMProvider`、`openai/ fallback / multi-provider` 切换、token 统计结构输出。
  - 验收：切换 `settings.ai_provider` 后不变更调用方。
  - 测试：模型调用 mock + 回退测试（未配置/异常时 fallback 触发）。

- [x] E5. 去重与聚类预处理（依赖：E3, E4）
  - 产出：`_normalize_url`、`cluster_id` 规则、热点 dedupe guard（`source_id + url`）。
  - 验收：同 URL 不重复入库；同义/标题变体聚合可追溯。
  - 测试：去重、规范化、归一化边界用例。

- [x] E6. 检测调度统一入口（依赖：E3, E4, E5）
  - 产出：手动/定时统一入口；任务链路顺序固定且记录成功/失败。
  - 验收：`active`/`filtered` 决策只来自统一 `is_analysis_active`。
  - 测试：手动触发 + 定时触发测试用例。

- [x] E7. RSS 输出与访问控制（依赖：E6）
  - 产出：`/rss/trending`、`/rss/keyword/{keyword_name}`、`/rss/user/{user_id}`，`rss_access_token` 支持。
  - 验收：XML 可解析，用户与关键词入口支持配置级鉴权。
  - 测试：XML 解析测试、token 校验测试。

- [x] E8. 报告与通知闭环（依赖：E6）
  - 产出：`/api/reports`、日报周报 markdown 生成、`/api/reports/{report_id}/html`。
  - 验收：仅聚合 `active` 热点；缺 SMTP 时仅跳过不阻塞主流程。
  - 测试：报告生成、SMTP absent 跳过测试、active/filtered 过滤测试。

- [x] E9. 前端 P0 最小可视化（依赖：E6, E8）
  - 产出：路由扩展到 `/app/analytics`，新增趋势聚合视图（趋势、来源排行、AI 重要性分布），并在 App Shell 与 Dashboard 增加可达入口。
  - 验收：前端可从工作台跳转到 `/app/analytics`，并展示趋势页三类卡片。
  - 测试：`AnalyticsClient` 在 API mock 或 E2E 快照下可稳定渲染三类卡片。

- [x] E10. 安全与运维补齐（依赖：E6）
  - 产出：新增 `RequestAuditMiddleware`（请求审计去敏）、`RateLimitMiddleware`（IP 60 秒窗口限流）和统一异常返回封装。
  - 验收：高频场景返回标准 `rate_limit` code，日志中不出现 token/authorization/cookie 明文。
  - 测试：`tests/test_mvp_services.py::test_rate_limit_middleware_blocks_excessive_requests` 与 `tests/test_mvp_services.py::test_error_response_is_structured_and_hides_stacktrace`。

- [x] E11. 企业级视图扩展（依赖：E10）
  - 产出：新增 `analytics_service` 及路由（`/api/analytics/trend`、`/api/analytics/sources`、`/api/analytics/sentiment`），并实现对应前端趋势页。
  - 验收：三接口在 `period_days` 约束下可返回结构化聚合值。
  - 测试：`tests/test_mvp_services.py::test_analytics_endpoints_return_aggregated_data`。

- [x] E12. 部署与运维加固（依赖：E1）
  - 产出：完善 backend/web Dockerfile、`nginx` 代理、`docker-compose.yml` 健康检查与 web 生产启动方式，并将后端测试与前端 `typecheck/build` 纳入 CI。
  - 验收：`docker compose up` 可形成 API/Web/Nginx 可用链路，CI 持续命中三类校验。
  - 测试：执行 `docker compose up -d` 与 `curl http://localhost:8080/api/health` 做回归 smoke。

## 2. 可并行建议

- 批次 P0-A（立即）：E1、E2、E3、E4
- 批次 P0-B（主链路）：E5、E6、E7、E8
- 批次 P0-C（交付与体验）：E9（可并行）, E10（可并行）
- 批次 P0-D（治理）：E11、E12

## 3. 任务完成定义

- 代码变更可编译并可执行相关测试。
- 与本任务对应的验收标准从 `docs/engineering/验收标准.md` 可见。
- 红绿测试证据可复用到 `PR`/任务交付说明中。
