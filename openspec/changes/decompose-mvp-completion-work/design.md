## Context

The project has completed the main MVP implementation pass and a Chinese documentation normalization pass. The remaining risk is not a missing monolithic feature, but fragmented acceptance: some capabilities are already covered by local tests, some require real external credentials, and some require manual browser review. The next pass should close these gaps without introducing non-P0 platform complexity.

Current constraints:

- Keep the stack as FastAPI, PostgreSQL, SQLAlchemy, Next.js, SMTP, and optional OpenAI-compatible model APIs.
- Keep primary documentation under `docs/` named in Chinese.
- Keep reports on `/api/reports` and `reports`; do not restore legacy daily-only endpoints or table names.
- Keep X/Twitter, Bing, SMTP, and model calls optional; missing credentials must not break the local MVP path.

## Goals / Non-Goals

**Goals:**

- Produce a decision-complete breakdown of remaining MVP completion work.
- Separate automated, real-credential, and manual browser acceptance gates.
- Identify the exact subsystems to inspect or fix before claiming the MVP is complete.
- Preserve lightweight self-hosted product boundaries.

**Non-Goals:**

- No new authentication, tenant, billing, realtime push, vector database, Redis, Celery, or complex queue platform.
- No API or schema compatibility work for legacy daily-report endpoints.
- No requirement that AI generate full report bodies in P0.
- No broad UI redesign beyond acceptance fixes needed for current workspace pages.

## Decisions

1. **Use readiness categories instead of a single done flag.**

   Automated checks, real-credential checks, and manual browser checks prove different things. The implementation pass should update acceptance docs and final delivery notes with the category each item belongs to.

2. **Treat credential-backed providers as optional integrations.**

   X/Twitter, Bing, SMTP, and OpenAI-compatible models must have two acceptance paths: local fallback/skip behavior and real configured-service behavior. Local tests can prove graceful degradation; only configured-service runs can prove provider integration.

3. **Keep reports template-first.**

   Daily and weekly reports should continue to use deterministic Markdown templates as the P0 baseline. AI report enhancement can be added later, but it must never block report generation.

4. **Make browser acceptance explicit.**

   Frontend typechecking is necessary but not enough. `/`, `/pricing`, `/app`, `/app/search`, and `/app/reports` must be reviewed in browser at desktop and mobile widths before the frontend is accepted as usable.

5. **Avoid changing business behavior while decomposing.**

   This change is a decomposition contract. Implementation tasks may later reveal small code or doc fixes, but the OpenSpec artifacts should first make the remaining work inspectable and schedulable.

## Risks / Trade-offs

- **Risk: Over-verifying optional providers in local development** -> Keep real-provider checks in a separate credentialed acceptance section.
- **Risk: Reintroducing old report naming through docs or tests** -> Add explicit drift checks for legacy daily-report strings in current source-of-truth files.
- **Risk: Treating browser review as subjective** -> Use concrete page list, viewport coverage, and overlap/overflow checks.
- **Risk: Scope expansion during cleanup** -> Keep non-goals visible in AGENTS, docs, tasks, and delivery summaries.

## Migration Plan

1. Audit current docs, OpenSpec specs, backend services, tests, and frontend pages against the new readiness categories.
2. Fix only gaps that block the existing MVP contract.
3. Add or adjust focused tests for local fallback, status semantics, report filtering, and legacy endpoint absence.
4. Run OpenSpec validation, backend tests, frontend typecheck/build, markdown-link checks, and browser acceptance.
5. Update the acceptance evidence in docs before committing.
