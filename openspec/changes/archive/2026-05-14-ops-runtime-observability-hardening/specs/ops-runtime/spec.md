# Ops Runtime & Observability Specification

## Purpose
The system SHALL expose lightweight runtime constraints and operational telemetry for the MVP so that deployment behavior and runtime health can be quickly verified without external APM.

## ADDED Requirements

### Requirement: Runtime constraints
The system SHALL expose and bind the runtime constraints to repository documentation and deployment steps.

#### Scenario: Runtime constraints documentation

- **WHEN** repository documents are used for bootstrap
- **THEN** they SHALL state explicitly that Python and Node run without mandatory virtual environments.
- **AND** repository MUST state PostgreSQL/Redis are bound to local `localhost` services（Homebrew-first default）.
- **AND** repository MUST state Docker remains optional and does not replace default local service startup.

### Requirement: Runtime telemetry
The system SHALL expose request and rate-limit runtime telemetry via a dedicated operations endpoint.

#### Scenario: Runtime telemetry

- **WHEN** any API request is processed
- **THEN** API layer SHALL increment request counters and status-code buckets.
- **AND** rate-limit blocks (`429`) SHALL increment a dedicated throttled counter.
- **WHEN** `GET /api/ops/metrics` is called
- **THEN** system SHALL return a stable JSON payload with request totals, status buckets, and rate-limit block metrics.

#### Scenario: Exposed ops metrics endpoint

- **GIVEN** the API receives traffic
- **WHEN** `GET /api/ops/metrics` is requested
- **THEN** response includes:
  - `metrics.total_requests`
  - `metrics.status_buckets`
  - `metrics.status_by_class`
  - `metrics.rate_limit_exceeded_total`
