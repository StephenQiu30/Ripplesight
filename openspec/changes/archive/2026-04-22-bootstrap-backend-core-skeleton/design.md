## Context

The product and OpenSpec baselines are now stable, but the codebase has no reusable backend implementation primitives yet. The first implementation slice needs to establish a layered backend core that can support source-governance and hotspot-discovery workflows without prematurely coupling business logic to FastAPI, Celery, PostgreSQL, Redis, or external data providers.

## Goals / Non-Goals

**Goals:**
- Add pure-domain entities and rules for source governance, normalized raw content, hotspot events, and evidence tracking.
- Add application services that orchestrate source listing, raw-content normalization, clustering, and scoring through repository protocols.
- Add in-memory infrastructure adapters so these flows are executable and unit-testable before persistence and external adapters exist.
- Add interface-layer pagination/query helpers aligned with the OpenAPI contract.

**Non-Goals:**
- Implement FastAPI routes, Celery jobs, database persistence, or third-party API integrations.
- Finalize production-grade clustering accuracy or scoring weights.
- Implement digest delivery, search indexing, or UI integration in this change.

## Decisions

### Decision: Keep the first slice dependency-free

The first backend skeleton will use only the Python standard library.

Rationale:
- The repository does not yet have a Python packaging baseline.
- This keeps the first slice easy to run and test while preserving future framework choice.

Alternatives considered:
- Introducing Pydantic/FastAPI models now: rejected because it would blur application and interface concerns too early.

### Decision: Use dataclasses for domain and interface models

Domain entities and DTO-style helpers will be represented with immutable or lightweight dataclasses.

Rationale:
- They are expressive, typed, and framework-agnostic.
- They fit the current goal of creating a reusable core rather than transport-bound models.

Alternatives considered:
- Plain dictionaries: rejected because they would make the initial contracts weak and harder to test.

### Decision: Put orchestration behind repository protocols

Application services will depend on repository protocols for sources, keyword rules, monitored accounts, and hotspot events.

Rationale:
- This matches the repository's layering rule that core logic should not depend directly on external SDKs or infrastructure details.
- It lets the same services later run against in-memory, database, or API-backed implementations.

Alternatives considered:
- Calling infrastructure classes directly from application services: rejected because it would collapse the layer boundary immediately.

### Decision: Start with deterministic title-based clustering and conservative X handling

The first clustering/scoring implementation will use normalized event keys derived from titles plus simple source-type weighting, including an explicit penalty for X-only evidence.

Rationale:
- It is enough to make the workflow executable and testable.
- It directly encodes one of the most important MVP constraints: X cannot decide the ranking by itself.

Alternatives considered:
- Delaying scoring until a later change: rejected because hotspot discovery without any ranking behavior would leave the core slice incomplete.

## Risks / Trade-offs

- [Simple clustering may merge too aggressively or not aggressively enough] -> Keep the rule deterministic now and refine it in later changes with better signals.
- [In-memory adapters are not production persistence] -> Use them only as a scaffold and preserve repository protocols so swapping implementations is straightforward.
- [OpenAPI contract coverage is still partial at code level] -> Limit this slice to DTO helpers and core services, then add service/API composition in a follow-up change.
- [Scoring constants may change later] -> Centralize them in the domain rule module so they are easy to revise.

## Migration Plan

1. Add domain models and hotspot-rule helpers.
2. Add application repository protocols and orchestration services.
3. Add in-memory infrastructure implementations.
4. Add interface DTO helpers.
5. Add unit tests for the first flows and validate the OpenSpec change.

## Open Questions

- Should the first API slice expose these services through read-only endpoints immediately, or wait until repository-backed persistence is in place?
- What additional fields beyond normalized title should become part of the long-term clustering fingerprint?
- What event-score normalization strategy should be adopted once real traffic and source distributions exist?
