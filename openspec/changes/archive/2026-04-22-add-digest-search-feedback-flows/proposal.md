## Why

The API layer now exposes source governance and hotspot event endpoints, but the remaining OpenAPI contract around daily digest retrieval, search, and feedback submission is still unimplemented. We need to complete those user-facing flows so the platform can serve the full MVP read path and the first feedback write path from a single assembled service.

## What Changes

- Extend the backend core with digest and feedback entities, repository protocols, and application services.
- Add in-memory digest and feedback repositories for the current API assembly.
- Add `/api/digests/today`, `/api/search`, and `/api/feedback` endpoints aligned with the existing contract baseline.
- Add tests covering digest retrieval, search behavior, and feedback submission.

## Capabilities

### New Capabilities
- `digest-search-feedback-api`: Provide the backend-core and API-layer support required for digest retrieval, hotspot search, and feedback submission flows.

### Modified Capabilities

## Impact

- `backend/core/`: New digest and feedback models, protocols, services, and in-memory adapters.
- `services/api/`: New digest/search/feedback route assembly and serialization logic.
- `tests/`: New API and core tests covering digest, search, and feedback behaviors.
- `openspec/`: New change artifacts plus archived spec delta for this flow.
