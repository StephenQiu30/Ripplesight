## 1. Foundation

- [x] 1.1 Create `frontend/web` runnable Next.js + TypeScript scaffold with shared layout and page shell.
- [x] 1.2 Add OpenAPI generation scripts (`api:gen`/`api:lint`/`api:check`) and a stable generated output path.
- [x] 1.3 Add API base URL configuration and local request wrapper that supports local dev base override and empty/error states.
- [x] 1.4 Update `docs/product/plan.md` stage5 section with operator-console traceability for OpenAPI generation and console key pages.
- [x] 1.5 Update `docs/engineering/acceptance.md` stage5 checklist with Stage 5 console and generation verification points.

## 2. Console UI

- [x] 2.1 Implement `/events` list page with topic/source filter and pagination using generated client for `GET /api/events`.
- [x] 2.2 Implement `/events/[id]` detail page with evidence links and 404/empty handling using `GET /api/events/{event_id}`.
- [x] 2.3 Implement `/search` page with query + pagination using `GET /api/search`.
- [x] 2.4 Implement operator feedback action flow using `POST /api/feedback` with success/failure states.
- [x] 2.5 Implement read-only config page(s) for `/api/sources`、`/api/x/keywords`、`/api/x/accounts`.

## 3. Validation & Acceptance

- [x] 3.1 Run `openspec status --change mvp-stage5-console-openapi-client-2026-04-25 --json` and confirm unblocked state for execution.
- [x] 3.2 Run `npm run api:gen` and `npm run api:check` in `frontend/web` and confirm generation consistency.
- [x] 3.3 Run frontend quality gates (`npm run lint`, `npm run typecheck`, `npm run build`) in `frontend/web`.
- [x] 3.4 Run backend test suite baseline (`python -m unittest discover -s tests`) and record pass/fail.
- [x] 3.5 Run `openspec validate --change mvp-stage5-console-openapi-client-2026-04-25` and `openspec validate --specs`.
