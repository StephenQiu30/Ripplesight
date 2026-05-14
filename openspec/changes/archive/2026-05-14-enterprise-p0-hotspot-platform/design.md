## Architecture Overview

This change adds a boundary-safe extension around the existing MVP:

- **Request layer**: add middleware stack for audit/limit/error handling.
- **Analytics layer**: dedicated read-only service and route set backed by existing models.
- **Operations layer**: Docker/Nginx process layout for single host deployment.
- **UI layer**: page-level analytics view under existing AppShell dashboard structure.

## Implementation Notes

- Keep middleware order consistent: unified error handlers first, rate limit and audit as ASGI middleware wrappers.
- Analytics endpoints remain read-only and query existing entities (`hotspots`, `ai_analyses`, `sources`).
- Deployment remains optional; API/Web services are first-class, PostgreSQL remains external.
