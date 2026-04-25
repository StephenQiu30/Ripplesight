## Why

阶段 4 已经具备了“有事件、有任务、有邮件发送路径”，但当前日报输出缺少可复核链路（事件摘要、来源证据）与降级行为说明。用户在依赖日报做日报阅览或人工复核时，当前链路不能区分渲染失败、单条事件缺失与完整投递成功。

我们需要在 MVP 不增量扩大范围的前提下，先补齐日报输出质量与可追踪性，做到“日报可读 + 可核验 + 失败可降级 + 状态可回溯”，保证阶段 4 能真正闭环落地。

## What Changes

- 增强日报渲染（`DigestRenderService`）：输出每条事件的中文摘要、来源证据清单（链接）和事件级别降级说明。
- 增强日报投递流程（`DigestDeliveryWorkflowService`）：将渲染失败或单事件异常处理成可持续执行的降级流程，并明确记录投递状态。
- 为现有邮件发送链路补齐验收可追溯信息（delivery_status）和测试断言，保证状态可追踪。
- 同步更新交付文档状态，阶段 4 在 `docs/product/plan.md` 与 `docs/engineering/acceptance.md` 里可见并可验收。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `digest-delivery`: 强化日报内容结构、证据链可读性、部分失败降级和投递状态行为。
- `worker-digest-delivery`：不作为独立变更项；本轮变更通过 `digest-delivery` 的工作流与状态行为实现。

## Impact

- 影响代码：`backend/core/application/services.py`（日报渲染与投递工作流）
- 影响测试：`tests/test_worker_digest_delivery.py`（新增降级与证据链断言）、`tests/test_api_routes.py`（必要时补充字段可读性断言）
- 影响文档：`docs/product/plan.md`、`docs/engineering/acceptance.md`（阶段 4 交付与验收勾选）
- 不涉及 OpenAPI、数据库 schema、新增 API 或外部依赖变更
