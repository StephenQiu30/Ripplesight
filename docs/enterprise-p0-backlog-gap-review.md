# 企业级 P0 Backlog 缺口复核（2026-05-24）

基于 `docs/engineering/验收标准.md`、`openspec/changes/archive/2026-05-14-enterprise-p0-hotspot-platform/tasks.md`、及本次代码变更进行的复核结果。

## 已补齐（已回归验证）

| 功能项 | PRD | Plan | 验收依据 |
|---|---|---|---|
| A2 LLM Provider 异常策略与可观测 | [docs/product/prd/06-LLM供应商切换与可观测性补齐PRD.md](./product/prd/06-LLM供应商切换与可观测性补齐PRD.md) | [docs/plans/13-LLM供应商切换与容错计划.md](./plans/13-LLM供应商切换与容错计划.md) | `settings` 增加 `AI_PROVIDER_ERROR_STRATEGY` 与 `AI_FALLBACK_PROVIDER`；`ai_analysis` 支持 fallback/skip/error 分支；日志事件 `ai_provider_selection`、`ai_provider_fallback`、`ai_provider_skip`；`tests/test_mvp_services.py` 覆盖关键路径。 |
| A4 聚类版本化回溯 | [docs/product/prd/07-热点聚类去重与版本化回溯PRD.md](./product/prd/07-热点聚类去重与版本化回溯PRD.md) | [docs/plans/14-热点聚类与回溯查询计划.md](./plans/14-热点聚类与回溯查询计划.md) | `run_hotspot_check` 写入 `cluster_id` / `cluster_version` / `clustered_at`；新增 `/api/hotspots/cluster/{cluster_id}`、`/api/hotspots/{id}/cluster-history`；单测覆盖版本递增与查询。 |
| A8 RBAC 最小权限 | [docs/product/prd/08-安全增强-RBAC与权限治理PRD.md](./product/prd/08-安全增强-RBAC与权限治理PRD.md) | [docs/plans/15-安全增强与RBAC计划.md](./plans/15-安全增强与RBAC计划.md) | `users.role` 持久化、`require_permission()` 依赖、关键路由接入；`tests/test_mvp_services.py` 覆盖 viewer/admin 权限边界。 |

## 仍需补齐的企业级 P0 缺口

1. **真实环境端到端**  
   - 空数据库初始化、真实 X/Twitter/Bing/SMTP/模型凭据场景仍需线下验收（当前为非阻塞降级能力已验证，尚未做生产链路回放）。

2. **企业级运维级验收**  
   - `docker compose` 真实联动（含 Nginx、API、Web）健康性验证、生产异常演练、日志脱敏审计证据仍需按运行环境补充。

3. **监控与告警闭环补充**  
   - `/api/ops/metrics` 与数据库指标已具备基础抓取指标，但未在该轮补齐告警阈值与告警渠道（邮件/短信）接入。

## 审核结论

- 本轮应优先把“未补齐”限定为**环境级与运维级验收缺口**，避免与已完成的后端功能补齐重复混淆。
- 当前后端功能补齐链条（A2、A4、A8）可进入提交；下一轮可从监控告警闭环与生产级稳定性场景启动。
