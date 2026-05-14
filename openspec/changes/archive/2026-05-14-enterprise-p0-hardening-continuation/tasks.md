---
change_name: enterprise-p0-hardening-continuation
version: "1.0.0"
status: draft
owner: "AI Architect"
---

# Enterprise P0 Hardening Continuation (low coupling)

## 1. Backend

- [x] 1.1 在 `apps/api/app/core/middleware.py` 添加代理头解析函数，支持 `X-Forwarded-For`、`X-Real-IP`。
- [x] 1.2 保持现有 `rate_limit` 响应结构（`error.code` 为 `rate_limit`）与限流窗口不变。

## 2. 测试

- [x] 2.1 在 `tests/test_mvp_services.py` 新增 `test_rate_limit_middleware_uses_forwarded_for` 用例。
- [x] 2.2 复跑 `python3 -m unittest tests.test_mvp_services`。
- [x] 2.3 复跑前端关键检查：`npm --prefix apps/web run typecheck` 与 `npm --prefix apps/web run build`。

## 3. 收尾

- [x] 3.1 检查变更不影响现有 RateLimit 旧用例与接口行为。
- [x] 3.2 生成 OpenSpec 验收并归档 change。
