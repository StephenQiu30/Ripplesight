## 1. 文档闭环

- [x] 1.1 在 `docs/product/plan.md` 标记阶段 4 的“日报与邮件闭环”交付完成项
- [x] 1.2 在 `docs/engineering/acceptance.md` 对阶段 4 两项验收打勾

## 2. 核心实现

- [x] 2.1 重构 `backend/core/application/services.py::DigestRenderService`，支持事件级渲染与中文摘要、证据链接展示
- [x] 2.2 调整 `DigestRenderService` 在单事件异常时降级处理，不影响其他事件输出
- [x] 2.3 调整 `DigestDeliveryWorkflowService` 的 `generate_and_deliver`，加入渲染失败回退和状态回写策略

## 3. 测试与验证

- [x] 3.1 新增/更新 `tests/test_worker_digest_delivery.py`：覆盖“含证据的渲染内容”和“单事件降级”
- [x] 3.2 新增/更新 `tests/test_worker_digest_delivery.py`：覆盖“渲染失败回退 + delivery_status 记录”
- [x] 3.3 运行相关测试并补齐快照断言，确认 API 只读链路仍返回 `delivery_status`
