## Why

The project now has a spec baseline, a backend core, and a read-oriented API surface, but it still lacks the worker orchestration layer that actually schedules digest generation and delivery. We need a worker/delivery slice so the MVP path from ranked events to generated digest to outbound email is executable through the intended Celery-based service boundary.

## What Changes

- Add worker-side Celery application assembly and beat schedule configuration under `services/worker`.
- Extend the backend core with digest rendering and email delivery orchestration abstractions.
- Add in-memory delivery adapters so digest generation and email sending can run deterministically without external providers.
- Add tests covering digest task orchestration, rendered content, and delivery status updates.

## Capabilities

### New Capabilities
- `worker-digest-delivery`: Provide the worker orchestration, digest rendering, and email delivery pipeline needed to execute the MVP digest workflow.

### Modified Capabilities

## Impact

- `services/worker/`: New Celery app, scheduled task entrypoints, and worker assembly.
- `backend/core/`: New digest-rendering and delivery orchestration services plus delivery adapter protocols.
- `pyproject.toml`: Add worker runtime dependencies needed for Celery-based execution.
- `tests/`: New worker and digest-delivery tests.
