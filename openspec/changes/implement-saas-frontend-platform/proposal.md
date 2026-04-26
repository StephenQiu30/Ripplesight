# Proposal: Implement SaaS Frontend Platform

## Why

The backend MVP now supports hotspot detection, immediate search, active/filtered status, notifications, and daily/weekly reports through `/api/reports`. The existing web app is still a simple console. The next stage needs a polished, private-deployable SaaS frontend so the product can be used directly without exposing implementation details.

## What Changes

- Replace the simple console shape with a light enterprise SaaS frontend.
- Add marketing entry pages at `/` and `/pricing`.
- Move the product workspace to `/app` and `/app/*`.
- Introduce Radix UI primitives and shadcn-style reusable UI components.
- Add workspace pages for dashboard, hotspots, search, keywords, sources, runs, reports, notifications, and settings.
- Consume the current FastAPI API surface only; do not add backend APIs in this change.
- Use `/api/reports` as the only report endpoint and keep `/api/daily-reports` absent.

## Impact

- Affected app: `apps/web`.
- Affected docs: front-end plan and implementation notes.
- New dependencies: Radix primitives, lucide icons, class variance and class merge helpers.
- No backend schema, route, authentication, tenant, or billing changes.

