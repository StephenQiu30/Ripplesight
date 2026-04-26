## 1. OpenSpec artifacts

- [x] Create proposal, design, specs, and tasks for the SaaS frontend platform.

## 2. Dependencies and UI system

- [ ] Add Radix UI primitives, lucide icons, class variance, clsx, and tailwind-merge dependencies.
- [ ] Create shadcn-style UI wrappers for buttons, inputs, tables, badges, cards, dialogs, selects, tabs, switches, tooltips, toast, and skeleton states.
- [ ] Add shared class helpers and root typography using `Plus Jakarta Sans`.

## 3. SaaS routes and shell

- [ ] Replace `/` with a SaaS product website homepage.
- [ ] Add `/pricing` with pricing placeholders and private-deployment messaging.
- [ ] Move the product workspace to `/app` and `/app/*`.
- [ ] Build a responsive app shell with sidebar navigation, top actions, and accessible focus states.

## 4. Workspace workflows

- [ ] Build `/app` dashboard from existing API data.
- [ ] Migrate hotspots, hotspot detail, keywords, sources, runs, notifications, and settings into `/app/*`.
- [ ] Add `/app/search` for immediate search using `/api/search`.
- [ ] Add `/app/reports` and `/app/reports/[id]` using `/api/reports`.
- [ ] Ensure mutation actions show loading, disabled, error, and empty states.

## 5. Validation

- [ ] Ensure frontend code and rendered text do not include `/api/daily-reports`.
- [ ] Run `npm --prefix apps/web run typecheck`.
- [ ] Run `npm --prefix apps/web run build`.
- [ ] Verify `/`, `/pricing`, `/app`, `/app/search`, and `/app/reports` with agent-browser.
- [ ] Verify mobile and desktop layouts do not overflow or overlap.

