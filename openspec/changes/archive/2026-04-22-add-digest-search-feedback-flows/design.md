## Context

The current API assembly now covers source governance and hotspot events, but the digest, search, and feedback portions of the OpenAPI baseline are still missing. The backend core also lacks digest and feedback primitives, which means the remaining contract gaps cannot be filled cleanly without extending the shared domain and application layers.

## Goals / Non-Goals

**Goals:**
- Add backend-core models and services for daily digests, event search, and feedback submission.
- Add in-memory repository support so the current API assembly can expose those flows deterministically.
- Expose `/api/digests/today`, `/api/search`, and `/api/feedback` from the FastAPI service.
- Add tests covering digest retrieval, search, and feedback persistence behavior.

**Non-Goals:**
- Implement production persistence, ranking refinement, or digest email delivery.
- Add authentication, rate limiting, or moderation rules for feedback.
- Change the previously implemented governance/event route behavior.

## Decisions

### Decision: Build digest data from the existing hotspot event set

The initial digest service will compose a daily digest from the current hotspot events instead of maintaining a separate ingest path.

Rationale:
- It keeps the slice aligned with the MVP workflow where digest content is derived from ranked events.
- It avoids inventing a second source of truth for digest content before persistence exists.

Alternatives considered:
- Hard-coding an independent digest payload: rejected because it would disconnect digest behavior from hotspot discovery.

### Decision: Implement search as event-title and summary matching over the in-memory event set

The first search implementation will query the available hotspot events in memory.

Rationale:
- It satisfies the contract-level need for search without adding infrastructure complexity.
- It remains consistent with the current scaffold stage of the repository.

Alternatives considered:
- Introducing database or full-text search now: rejected because it is too early in the stack evolution.

### Decision: Store feedback in a dedicated in-memory repository with generated identifiers

Feedback submissions will be accepted through a small application service that assigns IDs and timestamps.

Rationale:
- It creates a clean write-path boundary while keeping implementation simple.
- It prepares the shape for future persistence-backed replacement.

Alternatives considered:
- Writing feedback logic directly inside the route: rejected because it would bypass the core layer.

## Risks / Trade-offs

- [Digest content is derived from a small in-memory event set] -> Treat this as an integration scaffold and replace it with persisted digest generation later.
- [Search relevance is basic substring matching] -> Keep it explicit and upgrade later when persistence and indexing exist.
- [Feedback is ephemeral in memory] -> Preserve the repository boundary so persistence can be added without reworking API behavior.
- [OpenAPI contract still uses scaffold-level schemas] -> Keep serializers explicit so schema refinement stays localized.

## Migration Plan

1. Extend backend-core domain models, protocols, services, and in-memory repositories.
2. Add digest/search/feedback dependencies and serializers in the API layer.
3. Add the new API routes and tests.
4. Validate the change and archive it into the main spec set.

## Open Questions

- Should digest retrieval later return richer per-event metadata than the current simple `highlights` + `event_ids` structure?
- Should feedback support idempotency or duplicate protection once persistence is added?
