---
layer: Acceptance
doc_no: "2"
audience:
  - Tech-Lead
  - Dev
  - QA
feature_area: "area:infra area:api"
purpose: "记录 Go 服务基础工程与 OpenAPI 首个 feature PR 的可复测验收证据。"
canonical_path: "docs/acceptance/2-Go服务基础工程与OpenAPI验收.md"
status: approved
version: "1.0.0"
owner: "StephenQiu30"
inputs:
  - docs/product/prd/2-Go服务基础工程与OpenAPIPRD.md
  - docs/plans/2-Go服务基础工程与OpenAPI实现计划.md
outputs:
  - Go 服务基础工程验收证据
  - OpenAPI 导出验收证据
triggers:
  - "GitHub issue #72 状态变更"
downstream:
  - docs/plans/3-关键词与用户偏好实现计划.md
---

# 2-Go 服务基础工程与 OpenAPI 验收

## 1. 范围

本验收对应 GitHub issue `#72`，父 Epic 为 `#67`。

已完成内容：

1. 建立 Go module：`github.com/StephenQiu30/hotkey-server`。
2. 使用 Gin 作为 HTTP 服务框架。
3. 提供服务入口：`cmd/server/main.go`。
4. 提供配置加载：`internal/config`。
5. 提供健康检查：`GET /healthz`。
6. 提供 OpenAPI 导出：`GET /openapi.json`。
7. CI 接入 `go test ./...`。

## 2. 验证命令

```bash
go test ./...
git diff --check
HOTKEY_HTTP_ADDR=127.0.0.1:18080 go run ./cmd/server
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18080/openapi.json
```

## 3. 验证结果

- `go test ./...` 通过。
- `git diff --check` 通过。
- `/healthz` 返回 `{"service":"hotkey-server","status":"ok"}`。
- `/openapi.json` 返回 OpenAPI `3.1.0` 文档，并包含 `/healthz` 与 `/openapi.json` 路径。

## 4. 后续边界

PostgreSQL、pgvector、Redis 的真实连接、schema 初始化和读写测试将在后续 P0 数据与领域任务中继续补齐。本任务只建立基础配置入口与服务骨架，不隐式实现关键词、采集、相似聚合或日报能力。
