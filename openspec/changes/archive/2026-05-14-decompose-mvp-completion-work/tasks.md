## 1. Readiness Audit

- [x] 1.1 Audit `AGENTS.md`, `README.md`, and `docs/**` for current MVP scope, Chinese document naming, report API naming, and P0 non-goal boundaries.
- [x] 1.2 Audit `openspec/specs/**` and active `openspec/changes/**` for legacy report wording, missing weekly report expectations, and missing readiness evidence categories.
- [x] 1.3 Audit backend services and routes for source ingestion, check runs, search, reports, notifications, scheduler behavior, and legacy daily-report endpoint absence.
- [x] 1.4 Audit frontend workspace pages for `/`, `/pricing`, `/app`, `/app/search`, `/app/reports`, and backend API usage.
- [x] 1.5 Produce a gap list that classifies each item as automated verification, real-credential verification, manual browser verification, or deferred non-goal.

## 2. Backend MVP Completion

- [x] 2.1 Ensure all enabled source adapter failures are recorded without aborting the full check-run pipeline.
- [x] 2.2 Ensure missing X/Twitter and Bing credentials produce observable skipped or failed-source entries while other sources continue.
- [x] 2.3 Ensure search stays read-only, returns source errors, and does not persist hotspots or notifications.
- [x] 2.4 Ensure `active` status requires `relevance_score >= RELEVANCE_THRESHOLD` and `is_real is not False`.
- [x] 2.5 Ensure `filtered` hotspots do not send event emails and do not enter daily or weekly reports.
- [x] 2.6 Ensure daily and weekly reports use `/api/reports`, store `report_type`, and render from local Markdown templates.
- [x] 2.7 Ensure report sending records `report_id` notifications with `sent`, `failed`, or `skipped` status.
- [x] 2.8 Ensure scheduled check runs and scheduled reports use the same service paths as manual triggers.

## 3. Frontend Workspace Completion

- [x] 3.1 Ensure all workspace navigation links point to current pages and no frontend code or rendered text uses the legacy daily-report endpoint.
- [x] 3.2 Ensure `/app/search` calls `/api/search`, displays result status, and surfaces source errors.
- [x] 3.3 Ensure `/app/reports` and `/app/reports/[id]` call `/api/reports` for create, list, detail, and send flows.
- [x] 3.4 Ensure mutation buttons across keywords, sources, runs, reports, and settings have loading or disabled states.
- [x] 3.5 Verify empty, error, and loading states are visible and do not leave blank pages.
- [x] 3.6 Browser-review `/`, `/pricing`, `/app`, `/app/search`, and `/app/reports` at desktop and mobile widths for overlap, overflow, and unusable controls.

## 4. Documentation and Acceptance Evidence

- [x] 4.1 Update Chinese docs to record which MVP items are verified by automated checks, which require real credentials, and which require browser review.
- [x] 4.2 Keep primary `docs/` filenames in Chinese and update all markdown links after any rename or move.
- [x] 4.3 Record real-credential acceptance steps for X/Twitter, Bing, SMTP, and OpenAI-compatible model calls without requiring those credentials for local development.
- [x] 4.4 Ensure every API key, token, SMTP secret, and model credential is represented in `infra/env/.env.example` and local `infra/env/.env` with safe placeholder comments.
- [x] 4.5 Keep optional credential values empty by default so placeholder text is not treated as a configured secret.
- [x] 4.6 Keep report wording template-first and avoid describing AI-generated full reports as a P0 requirement.
- [x] 4.7 Keep deferred non-goals visible: multi-user auth, tenant isolation, billing, realtime push, vector search, Redis, Celery, and complex queues.

## 5. Verification and Delivery

- [x] 5.1 Run `openspec validate --all --json`.
- [x] 5.2 Run `.venv/bin/python -m unittest tests/test_mvp_services.py`.
- [x] 5.3 Run `npm --prefix apps/web run typecheck`.
- [x] 5.4 Run the project markdown-link check and legacy document-name drift checks.
- [x] 5.5 If frontend code changes, run `npm --prefix apps/web run build` and browser acceptance for the required pages.
- [x] 5.6 Summarize remaining gaps with their evidence category before commit or handoff.
