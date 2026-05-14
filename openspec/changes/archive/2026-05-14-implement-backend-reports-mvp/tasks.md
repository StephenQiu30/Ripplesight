## 1. OpenSpec artifacts

- [x] Create proposal, design, specs, and tasks for backend reports MVP.

## 2. Detection and search

- [x] Update active status semantics to require relevance threshold and `is_real is not False`.
- [x] Ensure `/api/search` initializes default sources, stays read-only, and uses the same status semantics.
- [x] Make Hacker News search query-capable when feasible.

## 3. Reports data model and API

- [x] Replace `daily_reports` with unified `reports` in SQL and SQLAlchemy models.
- [x] Replace `daily_report_id` notifications with `report_id`.
- [x] Remove `/api/daily-reports` route and daily-only schemas/services.
- [x] Add `/api/reports` create/list/detail/send endpoints.

## 4. Report generation and delivery

- [x] Generate daily and weekly Markdown reports from active hotspots only.
- [x] Support skipped/failed/sent SMTP notification records for reports.
- [x] Update scheduler settings and logic for optional daily and weekly report delivery.

## 5. Documentation and validation

- [x] Update README, env example, tech spec, and acceptance docs for reports.
- [x] Add backend tests for status semantics, search, reports, route registration, and SMTP fallback.
- [x] Run Python tests and OpenAPI route verification.
- [x] Verify FastAPI `/docs` with agent-browser.
