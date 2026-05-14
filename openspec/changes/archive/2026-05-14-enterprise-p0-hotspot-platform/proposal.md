## Why

The P0 enterprise extension needed practical readiness for production operation: safer API execution, minimal analytics observability, and deployment hardening. This change complements the existing MVP by closing gaps from monitoring, visualization, and operations.

## What Changes

- Add request rate limiting, request auditing, and unified error responses to improve reliability and security posture.
- Add lightweight analytics APIs and dashboard page for trend/source/importance views.
- Harden deployment and CI with API/Web Dockerfiles, Nginx routing, compose health checks, and CI checks.
- Clarify environment defaults for local PostgreSQL/Redis assumptions and local dev command usage.

## Impact

- Backend API: new middleware and `/api/analytics/*` endpoints.
- Frontend: new `/app/analytics` page and navigation links.
- Deployment: Docker Compose/Nginx topology and CI pipeline coverage.
- Operational docs: explicit local environment assumptions and startup commands.

## Acceptance Criteria

- Existing monitoring loop and report workflow remain operational.
- `enterprise-p0-hotspot-platform` tasks are executed and validated by tests.
- API/Frontend health and build checks pass in CI.
- Environment initialization uses local services as documented.
