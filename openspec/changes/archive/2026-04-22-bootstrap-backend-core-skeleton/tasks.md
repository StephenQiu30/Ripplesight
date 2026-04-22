## 1. Domain and interface foundations

- [x] 1.1 Add typed domain entities for source governance, normalized content, evidence links, and hotspot events
- [x] 1.2 Add interface-layer pagination and query helper models aligned with the current API contract

## 2. Application orchestration

- [x] 2.1 Add repository protocols for governance and hotspot workflows
- [x] 2.2 Add application services for listing governance records, normalizing raw items, clustering events, and scoring results

## 3. Infrastructure scaffolding

- [x] 3.1 Add in-memory repository implementations for the first workflow slice
- [x] 3.2 Wire module exports so later API and worker layers can import the new backend core primitives cleanly

## 4. Verification

- [x] 4.1 Add unit tests for governance filtering, deterministic clustering, and X-only ranking protection
- [x] 4.2 Run OpenSpec and Python test validation for the new backend core skeleton
