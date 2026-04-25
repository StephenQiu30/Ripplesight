## 1. Foundation

- [x] Add `sql/001_init_schema.sql` as the P0 schema source of truth.
- [x] Add SQLAlchemy models aligned with the SQL schema.
- [x] Add startup database initialization that executes the SQL schema file.
- [x] Update project docs to describe `sql/*.sql + SQLAlchemy` schema management.

## 2. Backend MVP

- [ ] Implement SQLAlchemy session management and repositories.
- [ ] Implement keyword CRUD and enable/disable APIs.
- [ ] Implement source configuration APIs and RSS/Hacker News ingestion adapters.
- [ ] Implement AI analysis service with OpenAI-compatible API and fallback behavior.
- [ ] Implement hotspot persistence, deduplication, list, detail, filter, and sort APIs.
- [ ] Implement SMTP notification delivery with success, failure, and skipped records.
- [ ] Implement manual check-run API and lightweight API-internal scheduled loop.

## 3. Console MVP

- [ ] Implement keyword management page.
- [ ] Implement sources and settings pages.
- [ ] Implement hotspot list/detail pages with filters and sorting.
- [ ] Implement check-run and notification status pages.
- [ ] Wire console actions to FastAPI endpoints.

## 4. Acceptance

- [ ] Verify empty PostgreSQL initializes from `sql/001_init_schema.sql`.
- [ ] Verify SQLAlchemy can create and read a keyword.
- [ ] Verify RSS and Hacker News both produce normalized candidates.
- [ ] Verify duplicate `(source_id, url)` hotspots are not inserted twice.
- [ ] Verify SMTP missing config does not stop the pipeline.
- [ ] Verify manual and scheduled checks share the same orchestration path.
