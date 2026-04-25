## Context

当前阶段 4 链路是：热点发现 -> `DigestService` 组装 -> `DigestRenderService` 渲染 -> `DigestDeliveryWorkflowService` 发送 -> worker 返回状态。  
现状问题主要有两点：
- 渲染内容过于精简，事件级证据与摘要缺失，不满足运营复核和人工跟踪场景。
- 渲染异常时会抛异常导致整条流程中断，工作流不能对可恢复/可降级场景持续交付。

MVP 边界不变：沿用现有内存仓储与 `RenderedDigestEmail`/`DailyDigest` 模型，不新增外部 API，先确保链路可执行和可观测。

## Goals / Non-Goals

**Goals:**
- 在不改 API 契约的前提下，增强日报正文：每条事件都输出中文摘要与证据链接清单。
- 让日报渲染具备“事件级隔离”与“整体降级”能力：单条事件缺失/异常不阻断整封邮件生成。
- 明确不同失败结果的 `delivery_status`，将投递结果保存在 `DailyDigest`，便于 `acceptance` 跟踪。

**Non-Goals:**
- 不新增邮件模板系统（例如 HTML/Jinja/多模版配置）。
- 不改 `contracts/openapi/openapi.yaml` 与外部接口。
- 不引入新的持久化模型（仍使用内存仓储/既有模型）与新的来源接入。

## Decisions

1. 在 `DigestRenderService` 内处理事件级构建错误（try/except）并记录 degrade note。
   - 备选：在上游服务先全量过滤无效事件。  
   - 取舍：上游过滤会影响链路透明度；在渲染阶段保留事件级输出记录可追溯且更接近复核场景。

2. 使用已有 `DailyDigest.delivery_status` 表达投递结果，不新增字段。
   - 备选：新增 delivery 状态对象字段。  
   - 取舍：新增模型会跨层扩散；当前阶段使用单值状态可满足“可追踪”目标且回滚简单。

3. 保持工作流在渲染失败时退化为“最小正文 + 失败说明”，仍尝试发送。
   - 备选：直接抛错并终止发送。  
   - 取舍：终止发送会导致“无内容可投递”失败；MVP 更强调每天日报有结果且可定位问题。

## Risks / Trade-offs

- [Risk] 逐步降级可能掩盖严重数据问题。  
  - Mitigation：降级邮件正文必须显式标记 `delivery_status`，并在 tests 覆盖渲染失败与单事件失败场景。
- [Risk] 增加降级分支可能让“成功”与“部分成功”边界模糊。  
  - Mitigation：定义固定状态字典，测试只允许本次变更认定的状态字符串。

## Migration Plan

- 逐个替换 `DigestRenderService` 和 `DigestDeliveryWorkflowService` 的实现，不改接口签名。
- 运行阶段 4 相关测试（`test_worker_digest_delivery`、`test_api_routes`，必要时补充 `test_digest_search_feedback_api` 的无关回归）。
- 验证通过后，更新 `plan.md` 与 `acceptance.md` 的阶段 4 标记并提交 change。
- 回滚方案：还原 `services.py` 对应方法到提交前版本，不影响路由与仓储。

## Open Questions

- 是否将“降级”邮件状态统一命名为 `partially_delivered`，以及上游是否需要展示该细分信息。当前先采用字符串常量内聚实现，后续可外置。
