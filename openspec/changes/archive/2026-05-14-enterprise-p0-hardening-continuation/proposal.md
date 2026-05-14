## Why

当前 `RateLimitMiddleware` 在反向代理场景下仍然仅按 `request.client.host` 做 IP 计数，容器/反向代理环境中会把多个真实用户归并到同一地址，导致限流误报。该补充 Change 以低耦合方式修复这一点，并补齐红绿测试回归。

## What Changes

- 在 `RateLimitMiddleware` 中优先使用标准代理头（`X-Forwarded-For`、`X-Real-IP`）提取客户端身份。
- 保持现有速率限制错误码与响应结构不变（`error.code=rate_limit`）。
- 补充单元测试覆盖代理头下的限流计算。

## Impact

- 后端安全与可观测面提升：在 Nginx/Compose 场景下 `rate_limit` 判定更真实。
- 风险低：仅影响限流中间件内的客户端标识提取，不改业务路由和存储结构。
- 验收边界：
  - `RATE_LIMIT_PER_MINUTE=1` 时，连续两次同一转发 IP 请求应触发 429。
  - 不同转发 IP 不共享该限流桶。

## Dependencies

- 不依赖新库，不影响现有外部接口。
