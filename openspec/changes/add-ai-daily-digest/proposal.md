## Why

The MVP can send one email per detected hotspot, but it cannot produce a daily summary for operators who want one concise AI digest instead of many event emails.

This change adds a lightweight AI daily digest flow that reuses existing hotspots, AI analyses, and SMTP delivery without introducing queues or a new frontend surface.

## What Changes

- Add a daily report data model for one report per date.
- Add a backend service that selects analyzed hotspots for a date and renders a concise digest.
- Add API endpoints to generate, send, list, and read daily reports.
- Extend notification records so SMTP delivery can be traced for daily reports as well as individual hotspots.
- Keep event notification behavior unchanged.

## Capabilities

### New Capabilities

- `daily-digest`: Generate and optionally email an AI daily digest from analyzed hotspots.

### Modified Capabilities

- `notification-delivery`: Notification records can be associated with either a hotspot event or a daily report.

## Impact

- Affected backend code: SQL schema, SQLAlchemy models, Pydantic schemas, FastAPI routes, notification service, scheduler service.
- Affected API surface: new `/api/daily-reports` endpoints.
- Affected persistence: new `daily_reports` table and optional `notifications.daily_report_id`.
- No new external dependencies.
