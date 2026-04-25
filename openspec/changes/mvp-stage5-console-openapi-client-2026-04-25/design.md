## Context

Current state is a runnable backend and API service, but `frontend/web` has only a placeholder `README.md`. Stage 5 acceptance is still incomplete because the control-plane pages are not implemented end-to-end.

We need to deliver:

- Frontend app initialization with Next.js and TypeScript.
- A contract-first frontend API layer that regenerates from the existing OpenAPI contract without changing the API surface.
- Console pages matching `operator-console` requirements: ranking, detail, search, feedback, and config browsing.

## Goals / Non-Goals

**Goals:**
- Deliver Stage 5 console read path on the existing MVP API set.
- Ensure API client files are reproducibly generated and committed from `contracts/openapi/openapi.yaml`.
- Keep implementation changes small, verifiable, and fully traceable to PRD Stage 5 and `operator-console` requirements.

**Non-Goals:**
- Introducing new API endpoints, response schemas, or schema-breaking backend changes.
- Implementing authentication, authorization, or role-based access.
- Introducing real-time push / websocket streaming.
- Backend logic migration (aggregation, scoring, and routing remain in existing services).

## Decisions

1. **Frontend stack: Next.js + TypeScript + App Router**
   - **Why:** Already consistent with Tech Spec and suitable for routing plus server/client component separation.
   - **Alternative:** Keep a non-framework static frontend. Rejected because it lacks maintainable routing and type integration overhead for future growth.

2. **API client generation flow using generated contract artifacts**
   - **Why:** Prevents schema drift and keeps frontend strongly typed with source-of-truth `contracts/openapi/openapi.yaml`.
   - **Implementation choice:** Add `api:gen` as an explicit script in `frontend/web/package.json`, outputting generated files to a stable path (`src/openapi/*`) and requiring generation before release.
   - **Alternative:** Hand-write API request helpers. Rejected because it reintroduces drift and weakens acceptance traceability.

3. **Generator determinism**
   - **Why:** Keep deliverability and reduce churn.
   - **Choice:** Use `@umijs/openapi` as the sole API generation tool and enforce `api:check` to fail when committed artifacts are out of sync with `contracts/openapi/openapi.yaml`.
   - **Alternative:** Multiple generators. Rejected due to unstable output signatures during handoffs.

## Risks / Trade-offs

- **Risk:** OpenAPI generator output may introduce noisy churn across environments.
  - Mitigation: pin generator versions, keep output directory stable, and add `api:check` to detect uncommitted diffs.
- **Risk:** Frontend build environment differs from backend (ports, paths), causing API fetch failures during local dev.
  - Mitigation: define `NEXT_PUBLIC_API_BASE_URL` and provide a local proxy route strategy in the Next config.
- **Risk:** Control UI may outpace backend behavior expectations on error handling.
  - Mitigation: include minimal error/empty states for 404/400 and API timeouts in each page.

## Migration Plan

1. Create and verify `frontend/web` runnable app.
2. Add API generation and scripts.
3. Generate and commit API client artifacts.
4. Implement five UI blocks (list/detail/search/feedback/config).
5. Run OpenSpec and tests, then update docs checklist.

No data migration is required because APIs remain unchanged.

## Open Questions

- Which generated-client format should be used for component usage (`service` methods vs. hook helpers)?
  - **Default assumption:** function-based service methods for direct import in client components to minimize learning overhead.
