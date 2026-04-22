## Why

The backend core skeleton already provides domain models, application services, and in-memory adapters, but nothing exposes that functionality through HTTP yet. We need a read-only API assembly layer so the repository can serve the first contract-aligned endpoints and give later frontend and worker work a stable integration surface.

## What Changes

- Add a FastAPI-based read-only API assembly for source governance and hotspot discovery endpoints.
- Add API response models and route wiring aligned with the existing OpenAPI baseline.
- Add development dependency declarations for the API runtime and API tests.
- Add API tests that verify the first read-only routes and their pagination/filter behavior.

## Capabilities

### New Capabilities
- `read-only-api-assembly`: Provide the HTTP service bootstrap, route assembly, and response shaping needed to expose the first read-only backend workflows.

### Modified Capabilities

## Impact

- `services/api/`: New FastAPI app, route modules, dependency wiring, and bootstrap data.
- `backend/core/`: Reused as the business-logic source; no new domain behavior required.
- `contracts/openapi/openapi.yaml`: Kept as the contract reference for route alignment.
- `pyproject.toml`: New dependency and tooling baseline for the API slice.
- `tests/`: New API route tests.
