# ops-deploy Specification

## Purpose
TBD - created by archiving change enterprise-p0-hotspot-platform. Update Purpose after archive.
## Requirements
### Requirement: Deployment and CI hardening

The system SHALL provide reusable deployment and CI coverage.

#### Scenario: Compose health and endpoint smoke

- **WHEN** docker compose starts API/Web/Nginx services
- **THEN** API health endpoint `/api/health` is reachable
- **AND** web console is reachable through Nginx

#### Scenario: CI coverage for backend and frontend

- **WHEN** CI pipeline runs backend test and frontend checks
- **THEN** unit tests, `typecheck`, and production build all pass
- **AND** failures are surfaced before merge

