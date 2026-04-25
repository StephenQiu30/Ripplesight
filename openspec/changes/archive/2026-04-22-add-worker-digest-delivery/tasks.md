## 1. Worker and core foundations

- [x] 1.1 Add worker runtime dependencies and Celery application assembly under `services/worker`
- [x] 1.2 Extend the backend core with digest rendering and delivery gateway abstractions plus in-memory adapters

## 2. Digest workflow execution

- [x] 2.1 Add worker task entrypoints that generate and deliver the daily digest through backend-core services
- [x] 2.2 Add deterministic bootstrap wiring so the worker can run against the current in-memory event and digest data

## 3. Verification and publication

- [x] 3.1 Add automated tests for worker task execution, digest rendering, and delivery status transitions
- [x] 3.2 Validate the OpenSpec change, run the Python test suite, and archive the completed change
