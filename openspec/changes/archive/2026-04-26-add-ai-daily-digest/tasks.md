## 1. OpenSpec

- [x] Create proposal, design, specs, and tasks for AI daily digest.

## 2. Persistence

- [x] Add `daily_reports` table to `sql/001_init_schema.sql`.
- [x] Add `daily_report_id` support to notification schema and model.
- [x] Add SQLAlchemy `DailyReport` model and Pydantic schemas.

## 3. Backend Service

- [x] Implement daily digest generation from analyzed hotspots.
- [x] Implement SMTP sending and notification recording for daily reports.
- [x] Add lightweight scheduler support for optional daily digest delivery.

## 4. API

- [x] Add daily report generate, send, list, and detail endpoints.
- [x] Register daily report routes in FastAPI.

## 5. Docs

- [x] Update README and technical docs with AI daily digest behavior.
