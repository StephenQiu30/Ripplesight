## Context

The repository now covers the main API surface and the supporting backend core, but the worker service still has no executable task assembly. The MVP path described by the specs requires a scheduled workflow that takes hotspot events, renders a digest, and sends it through an email delivery boundary without duplicating business logic outside `backend/core/`.

## Goals / Non-Goals

**Goals:**
- Add a Celery-based worker assembly under `services/worker`.
- Extend the backend core with digest rendering and delivery orchestration services plus adapter protocols.
- Add an in-memory email delivery adapter so the workflow is deterministic and testable.
- Add tests for task orchestration, digest rendering, and delivery status updates.

**Non-Goals:**
- Connect to real Redis, Resend, or external model providers.
- Implement collection scheduling for every upstream source.
- Introduce production deployment or monitoring configuration in this change.

## Decisions

### Decision: Use Celery for the worker boundary but default to eager/local execution in tests

The worker slice will assemble a real Celery app while using local configuration that keeps tests deterministic.

Rationale:
- It matches the documented technical direction (`Celery + Redis`) without forcing infrastructure setup in the current repository stage.
- It lets us validate task boundaries and beat configuration immediately.

Alternatives considered:
- Using plain Python functions only: rejected because it would skip the worker boundary the repository explicitly reserves for `services/worker`.

### Decision: Keep digest rendering inside the backend core

Digest formatting and delivery orchestration will be implemented as backend-core application services rather than worker-only helpers.

Rationale:
- The worker should assemble and trigger tasks, not own business logic.
- This keeps digest logic reusable for later preview or replay flows.

Alternatives considered:
- Rendering digest bodies directly inside Celery tasks: rejected because it would duplicate domain/application behavior in the worker layer.

### Decision: Add a delivery gateway protocol with an in-memory adapter

The first delivery implementation will capture outbound emails in memory with explicit status updates.

Rationale:
- It provides a clean seam for later Resend integration.
- It keeps the digest pipeline verifiable without external credentials.

Alternatives considered:
- Hard-coding print/log output only: rejected because it would not model delivery state as a replaceable adapter.

## Risks / Trade-offs

- [Celery configuration may diverge from eventual Redis-backed deployment] -> Keep configuration centralized and simple so real transport setup can replace defaults later.
- [Digest body rendering is still simplistic without LLM integration] -> Treat the renderer as a scaffold and preserve adapter boundaries for later summarization improvements.
- [In-memory delivery does not persist history] -> Keep the delivery protocol explicit so persistence-backed delivery records can be introduced cleanly.
- [Worker tests can become flaky if they depend on asynchronous execution] -> Use eager task execution in tests and unit-test orchestration services directly.

## Migration Plan

1. Add worker runtime dependencies and a Celery application factory.
2. Extend backend-core with digest rendering and delivery orchestration primitives.
3. Add in-memory delivery adapters and worker tasks that call backend-core services.
4. Add tests for task execution, rendered content, and delivery status.
5. Validate and archive the completed change.

## Open Questions

- Should future collection scheduling live in the same Celery app or a separate queue namespace?
- What exact email template and recipient model should the real Resend integration adopt once credentials and user scope are finalized?
