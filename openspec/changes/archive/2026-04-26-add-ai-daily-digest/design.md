## Overview

AI daily digest is a backend-only MVP capability. It aggregates already-ingested hotspots and their AI analyses for a given date, stores the generated report, and can send that report through the existing SMTP configuration.

The digest is intentionally deterministic and lightweight: no new queue, no Redis, no separate worker, and no frontend page in this change.

## Data Model

Add `daily_reports`:

- `id`
- `report_date`
- `status`
- `subject`
- `summary`
- `content`
- `hotspot_count`
- `sent_at`
- timestamps

Extend `notifications`:

- `daily_report_id` nullable FK to `daily_reports`

This keeps individual hotspot emails and daily digest emails in the same delivery audit trail.

## API

- `POST /api/daily-reports`
  - Generate or refresh a report for a date.
- `POST /api/daily-reports/{report_id}/send`
  - Send an existing report by SMTP.
- `GET /api/daily-reports`
  - List reports.
- `GET /api/daily-reports/{report_id}`
  - Read one report.

## Digest Selection

The report uses hotspots whose `fetched_at` falls within the selected day in UTC. It prioritizes:

- high importance before medium and low
- higher relevance score
- newer fetched time

The MVP keeps content generation local and deterministic. If a report has no analyzed hotspots, it still stores a report with `hotspot_count = 0` and a clear empty-state summary.

## SMTP Delivery

Daily digest SMTP delivery reuses existing SMTP settings. Missing SMTP config records a skipped notification and does not fail report generation.

## Scheduler

The existing API-internal scheduler remains lightweight. If daily digest scheduling is enabled, it can generate and send yesterday's digest once per process per date.

## Non-goals

- No frontend page.
- No multi-recipient management.
- No queue, retry scheduler, or Celery/Redis.
- No AI-written long-form newsletter in this change.
