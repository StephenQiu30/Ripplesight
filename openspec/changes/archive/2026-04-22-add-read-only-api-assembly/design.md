## Context

The repository now has a validated specification baseline and a reusable backend core skeleton, but `services/api/` still contains only documentation. The next useful slice is to expose the first read-only endpoints through FastAPI while keeping business logic inside `backend/core/` and using in-memory bootstrap data until persistence is introduced.

## Goals / Non-Goals

**Goals:**
- Add a FastAPI application factory and route modules under `services/api/`.
- Expose read-only routes for `/api/sources`, `/api/x/keywords`, `/api/x/accounts`, `/api/events`, and `/api/events/{id}`.
- Shape responses to match the current OpenAPI baseline closely enough for early integration.
- Add automated API tests using FastAPI `TestClient`.

**Non-Goals:**
- Implement write endpoints, background workers, digest delivery, search, or feedback submission.
- Introduce database persistence or external API clients.
- Rework backend core domain rules during this change.

## Decisions

### Decision: Use FastAPI directly in the service layer and keep route logic thin

The service layer will create the `FastAPI` app and register routers, while route handlers only orchestrate dependencies and response mapping.

Rationale:
- This follows the repository rule that `services/api/` is only responsible for startup, assembly, and route mounting.
- It keeps business rules reusable across API and worker layers.

Alternatives considered:
- Embedding business logic in route handlers: rejected because it would violate the layering rule immediately.

### Decision: Introduce a minimal `pyproject.toml` for runtime and test dependencies

This change will declare FastAPI, Uvicorn, and HTTPX in a simple project baseline so the API slice is installable and testable.

Rationale:
- FastAPI and its test stack are not currently installed in the environment.
- A project-level dependency declaration is cleaner than relying on ad hoc local installs.

Alternatives considered:
- Postponing dependency declaration until more services exist: rejected because it would make this slice hard to run or verify.

### Decision: Use in-memory bootstrap data behind dependency factories

The API routes will depend on service factories that assemble in-memory repositories and sample data.

Rationale:
- It gives the first API slice deterministic behavior without committing to persistence design.
- It allows tests to verify contract-level behavior immediately.

Alternatives considered:
- Hard-coding dict responses directly in route handlers: rejected because it would bypass the backend core and create throwaway code.

### Decision: Return serialized dictionaries from service-backed mappers

The route layer will serialize backend core entities into OpenAPI-aligned response payloads.

Rationale:
- The current backend core intentionally uses framework-agnostic dataclasses.
- Explicit mappers make the contract boundary visible and easy to refine later.

Alternatives considered:
- Replacing dataclasses with Pydantic in the core: rejected because it would couple the core to FastAPI concerns.

## Risks / Trade-offs

- [OpenAPI alignment may still be approximate because the contract is scaffold-level] -> Keep field mapping explicit and refine the contract in later changes instead of hiding mismatches.
- [In-memory bootstrap data is not real persistence] -> Treat it as a deterministic integration scaffold only.
- [Installing new dependencies may introduce environment drift] -> Declare them in `pyproject.toml` and verify with tests immediately.
- [Route count may expand quickly] -> Limit this slice to read-only governance and event endpoints.

## Migration Plan

1. Add dependency declarations for the API runtime and tests.
2. Implement FastAPI app creation, dependencies, serializers, and routers.
3. Add deterministic bootstrap data wired through backend core services.
4. Add API tests for route behavior and filtering.
5. Validate the OpenSpec change and archive it after implementation.

## Open Questions

- Should the later persistence-backed API preserve the same dependency factory shape, or should it move to a more explicit container pattern?
- Which endpoint should be the first to switch from in-memory bootstrap data to repository-backed storage?
