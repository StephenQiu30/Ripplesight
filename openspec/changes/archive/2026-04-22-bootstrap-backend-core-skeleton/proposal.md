## Why

The repository now has a validated product/spec baseline, but the backend implementation surface is still only directory placeholders. We need a minimal backend core skeleton so source governance and hotspot discovery can move from requirements into executable code without violating the repository's layering and OpenAPI-first constraints.

## What Changes

- Add typed backend-core domain models for source governance and hotspot discovery workflows.
- Add application-level services and repository protocols that orchestrate listing, normalization, clustering, and scoring without binding business logic to frameworks.
- Add in-memory infrastructure adapters so the first implementation slice is runnable and testable before external databases or APIs are wired in.
- Add interface-layer pagination and query DTO helpers plus unit tests for the first orchestration paths.

## Capabilities

### New Capabilities
- `backend-core-skeleton`: Provide the reusable domain, application, interface, and in-memory infrastructure foundation required to implement the first MVP backend workflows.

### Modified Capabilities

## Impact

- `backend/core/domain/`: New domain entities and hotspot rules.
- `backend/core/application/`: New repository protocols and orchestration services.
- `backend/core/infrastructure/`: New in-memory repository adapters for early execution and tests.
- `backend/core/interface/`: New pagination/query DTO helpers aligned with the API baseline.
- `tests/`: New unit tests covering the initial backend core skeleton.
