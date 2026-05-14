## Why

The MVP already has the main backend loop, frontend workspace, and Chinese documentation baseline, but acceptance still mixes code-path verification, real-credential verification, manual browser review, and future non-goals. This change decomposes the remaining work into explicit OpenSpec contracts so the next implementation pass can finish the MVP without expanding into a heavy platform.

## What Changes

- Add a clear MVP readiness contract that separates automated checks, real-credential checks, manual browser checks, and deferred work.
- Tighten source integration requirements around optional external credentials and observable skip/failure behavior.
- Tighten report requirements around template-first daily/weekly reports, active-hotspot filtering, and report notification status.
- Tighten workspace acceptance requirements around connected backend flows, responsive browser review, and no legacy report endpoint usage.
- Add implementation tasks that identify what to inspect, what to fix, what to test, and what to leave out of P0.

## Capabilities

### New Capabilities

- `mvp-readiness-governance`: Defines the final MVP readiness gates, evidence categories, and non-goal boundaries.

### Modified Capabilities

- `source-ingestion`: Clarifies optional external-source credential behavior and real-credential verification expectations.
- `daily-digest`: Clarifies template-first daily/weekly report behavior and active-hotspot-only aggregation.
- `notification-delivery`: Clarifies event/report email delivery status and SMTP-missing fallback.
- `operator-console`: Clarifies workspace browser acceptance, backend-connected flows, and legacy endpoint absence.
- `check-run-orchestration`: Clarifies shared manual/scheduled orchestration and acceptance evidence.

## Impact

- Affected docs and OpenSpec artifacts: `AGENTS.md`, `README.md`, `docs/**`, `openspec/specs/**`, and this change directory.
- Affected backend verification surfaces: source adapters, check runner, search, reports, notifications, scheduler, and tests.
- Affected frontend verification surfaces: `/`, `/pricing`, `/app`, `/app/search`, `/app/reports`, and workspace data pages.
- No new runtime dependency is expected; P0 remains FastAPI, PostgreSQL, SQLAlchemy, Next.js, SMTP, and optional OpenAI-compatible model APIs.
