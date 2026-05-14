# security-gate Specification

## Purpose
TBD - created by archiving change enterprise-p0-hotspot-platform. Update Purpose after archive.
## Requirements
### Requirement: Request observability and rate protection

The system SHALL provide basic request auditing and rate protection for API safety.

#### Scenario: Audit log sanitization

- **WHEN** a request contains `authorization` or `cookie`
- **THEN** audit log records only masked values

#### Scenario: Per-ip rate limiting

- **WHEN** same client exceeds configured request budget in one minute
- **THEN** API returns HTTP 429
- **AND** response uses unified error code `rate_limit`

