## ADDED Requirements

### Requirement: Rate limit identification via trusted proxy headers

The API request rate limiting SHALL resolve client identity from proxy metadata before fallback host extraction to ensure fair throttling under reverse-proxy or Docker topologies.

#### Scenario: Forwarded IP throttling

- **WHEN** `RateLimitMiddleware` sees two requests from the same `X-Forwarded-For` value within the same window
- **THEN** the second request returns `429`
- **AND** the error payload contains `error.code=rate_limit`

#### Scenario: Different forwarded IPs have independent buckets

- **WHEN** a request is made with `X-Forwarded-For: 203.0.113.17` and another with `X-Forwarded-For: 198.51.100.9`
- **THEN** they are counted in different buckets when `RATE_LIMIT_PER_MINUTE` is low
- **AND** one bucket hitting limit does not affect the other
