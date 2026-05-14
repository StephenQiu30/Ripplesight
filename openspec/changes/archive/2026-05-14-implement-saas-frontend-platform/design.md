# Design: SaaS Frontend Platform

## Product Model

The first SaaS frontend release is a single-user private deployment product. It should feel like a deliverable SaaS platform, but it does not implement public multi-user authentication, organizations, billing, permissions, or Stripe.

The route model is:

- `/` for the product website.
- `/pricing` for pricing plan placeholders.
- `/app` for the application dashboard.
- `/app/*` for workspace workflows.

## UI System

Use Tailwind CSS with Radix UI primitives and shadcn-style local wrappers. Components should live under `src/components/ui/*` and be reusable by all pages. Use `lucide-react` for icons and do not use emoji as UI icons.

Use `Plus Jakarta Sans` through `next/font/google` at the root layout. The visual style is light enterprise SaaS: `#F8FAFC` background, navy/blue primary surfaces, amber/orange accent for important CTA states, restrained borders, clear focus rings, and dense but scannable content.

## Data Flow

Keep the existing `NEXT_PUBLIC_API_BASE_URL` client model. Extend the API client with report and search types, but do not add a backend aggregation route. Dashboard metrics can be derived from existing list responses.

Reports must use `/api/reports`. The old `/api/daily-reports` string must not appear in frontend code or rendered text.

## UX Rules

All mutation actions must expose loading and disabled states. Request errors must be visible near the action or in a toast. Empty lists must have designed empty states. Tables should use structured table components on desktop and must not overflow mobile layouts.

## Verification

Run TypeScript checks and production build. Then verify key routes in a browser with desktop and mobile widths, including `/`, `/pricing`, `/app`, `/app/search`, and `/app/reports`.

