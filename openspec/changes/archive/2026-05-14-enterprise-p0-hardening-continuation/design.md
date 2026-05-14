## Design

### 变更范围

- 修改文件：
  - `apps/api/app/core/middleware.py`
- 新增/更新测试：
  - `tests/test_mvp_services.py`（RateLimit 相关新增场景）

### 实现思路

- `RateLimitMiddleware` 在读取客户端地址时，不再只读取 `request.client.host`，而是按以下顺序获取：
  1. `X-Forwarded-For` 的首个 IP（取最左侧）
  2. `X-Real-IP`
  3. `request.client.host`
  4. `"anonymous"`
- 保持原有 `_RateBucket` 的计数窗口（60 秒）与 `X-RateLimit-*` 响应头逻辑不变。
- 在测试中使用 `TestClient` 和不同 `X-Forwarded-For` 值验证：
  - 同一 `X-Forwarded-For` 下第二次请求触发 429；
  - 不同 `X-Forwarded-For` 不共享限流计数。

### 风险与回退

- 风险：代理头不可信时可能被伪造。该场景仅用于限流边界，后续可与网关层信任策略联动。
- 回退：移除头解析逻辑并恢复 `request.client.host` 即可恢复旧行为。
