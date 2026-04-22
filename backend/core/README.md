# Backend Core

这里存放后端共享领域代码，是 `services/api` 与 `services/worker` 的共同依赖层。

分层约束：

- `domain/`：领域模型与核心规则
- `application/`：用例编排和流程组织
- `infrastructure/`：外部适配器
- `interface/`：DTO、统一错误结构和接口边界辅助对象

禁止事项：

- 禁止在 `services/api` 与 `services/worker` 中复制这里的逻辑
- 禁止业务层直接依赖第三方 SDK
