## Why

The backend has a working MVP-shaped loop, but the current implementation still exposes the old daily-only report API and lacks weekly reports. Search and hotspot status handling also need to match the current MVP rules before the backend can be accepted as a complete closed loop.

## What Changes

- Strengthen hotspot and search status semantics so `is_real is False` cannot become `active`.
- Ensure immediate search has default sources available and does not persist hotspots.
- Replace daily-only report APIs and storage with a unified `reports` model and `/api/reports` API.
- Support daily and weekly report generation with template-first Markdown output.
- Send report emails through the same SMTP notification recording path.
- Update scheduler configuration for optional daily and weekly report delivery.
- Add focused backend tests and API documentation verification.

## Impact

- Backend services: check runner, search, reports, notification, scheduler.
- API surface: add `/api/reports`; remove `/api/daily-reports`.
- Database schema source: replace `daily_reports` with `reports`; replace `notifications.daily_report_id` with `notifications.report_id`.
- Documentation: README, tech spec, acceptance criteria, environment example.
