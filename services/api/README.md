# API Service

该目录只承担 `FastAPI` 服务的启动、装配和路由挂载职责。

约束：

- 不在此目录堆放核心业务逻辑
- 业务规则统一复用 `backend/core/`
- 所有 HTTP 接口必须先对齐 `contracts/openapi/openapi.yaml`
