## Why

Stage 5 is currently blocked by unstable frontend delivery assumptions: no local app scaffold, no API type-sync strategy, and no contract-driven API client generation process. This change adds the missing foundation so the operator console can be delivered under the existing MVP API boundary without introducing interface drift.

## What Changes

- Bootstrap `frontend/web` into a runnable `Next.js + TypeScript` console application for Stage 5 pages.
- Add reproducible OpenAPI client generation from `contracts/openapi/openapi.yaml`, including a reviewable generated output directory under version control.
- Implement MVP console pages using generated API types and a unified client layer: today list, event detail, search, feedback action, and read-only configuration views.
- Reuse the existing Stage 5 acceptance surface from PRD and map implementation progress into task tracking and doc checklists.
- Update `docs/product/plan.md` and `docs/engineering/acceptance.md` with Stage 5 delivery and verification points for API generation and console pages.

## Capabilities

### New Capabilities
- none

### Modified Capabilities
- `operator-console`: Implement the MVP console execution path in frontend with OpenAPI-generated API client consumption, including list/detail/search/feedback flows and read-only config viewing.

## Impact

- Frontend: introduce `frontend/web` app bootstrap, generated API clients, page routes, and shared UI types.
- Tooling: add reproducible OpenAPI generation scripts and audit checks in `frontend/web/package.json`.
- Documentation: update stage delivery traceability in `docs/product/plan.md` and `docs/engineering/acceptance.md`.
- No API surface changes: all endpoints remain as currently defined in `contracts/openapi/openapi.yaml`.
