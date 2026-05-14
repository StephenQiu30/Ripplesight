## 1. OpenSpec artifacts

- [x] Create proposal, design, specs, and tasks for the SaaS frontend platform.

## 2. Dependencies and UI system

- [x] Add Radix UI primitives, lucide icons, class variance, clsx, and tailwind-merge dependencies.
- [x] Create shadcn-style UI wrappers for buttons, inputs, tables, badges, cards, dialogs, selects, tabs, switches, tooltips, toast, and skeleton states.
- [x] Add shared class helpers and root typography using `Plus Jakarta Sans`.

## 3. SaaS routes and shell

- [x] Replace `/` with a SaaS product website homepage.
- [x] Add `/pricing` with pricing placeholders and private-deployment messaging.
- [x] Move the product workspace to `/app` and `/app/*`.
- [x] Build a responsive app shell with sidebar navigation, top actions, and accessible focus states.

## 4. Workspace workflows

- [x] Build `/app` dashboard from existing API data.
- [x] Migrate hotspots, hotspot detail, keywords, sources, runs, notifications, and settings into `/app/*`.
- [x] Add `/app/search` for immediate search using `/api/search`.
- [x] Add `/app/reports` and `/app/reports/[id]` using `/api/reports`.
- [x] Ensure mutation actions show loading, disabled, error, and empty states.

## 5. Validation

- [x] Ensure frontend code and rendered text do not include `/api/daily-reports`.
- [x] Run `npm --prefix apps/web run typecheck`.
- [x] Run `npm --prefix apps/web run build`.
- [x] Verify `/`, `/pricing`, `/app`, `/app/search`, and `/app/reports` with agent-browser.
- [x] Verify mobile and desktop layouts do not overflow or overlap.
