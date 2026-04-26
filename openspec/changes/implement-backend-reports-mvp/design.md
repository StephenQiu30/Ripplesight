## Overview

Implement the current backend MVP closed loop without adding frontend work or heavy infrastructure. The implementation remains synchronous and SQLAlchemy-based.

## Hotspot and Search Semantics

Hotspot detection and immediate search use the same active-status rule: a result is `active` only when relevance is at or above `RELEVANCE_THRESHOLD` and the AI result is not explicitly false. Search stays read-only and does not create `hotspots`, `ai_analyses`, or notifications.

## Reports

Reports replace the old daily-only concept. A report has a `report_type` of `daily` or `weekly`, a UTC period start/end, status, subject, summary, content, hotspot count, and optional send timestamp. The uniqueness boundary is `report_type + period_start + period_end`.

Daily reports cover one UTC day. Weekly reports cover an ISO week from Monday 00:00:00 to the following Monday 00:00:00. Generated reports include only `active` hotspots. Report content is Markdown rendered from a deterministic template. AI can be added later as an enhancement, but report generation must not depend on it.

## Notifications and Scheduler

Report emails reuse SMTP notification records. Missing SMTP records `skipped`; SMTP failures record `failed` without rolling back report generation. The lightweight scheduler can optionally generate yesterday's daily report and the previous complete weekly report.

## Non-goals

- No console UI work.
- No Redis, Celery, queue, vector database, or task platform.
- No old data migration; schema reset is acceptable for this MVP.
- No compatibility route for `/api/daily-reports`.
