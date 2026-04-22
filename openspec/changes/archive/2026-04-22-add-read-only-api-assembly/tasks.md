## 1. Runtime baseline

- [x] 1.1 Add project dependency declarations for FastAPI, Uvicorn, and HTTPX-based API testing
- [x] 1.2 Install the API dependencies needed to run and verify the service slice

## 2. API assembly

- [x] 2.1 Add the FastAPI application factory, dependency wiring, and bootstrap data assembly under `services/api`
- [x] 2.2 Add read-only routes and serializers for sources, X governance records, and hotspot events

## 3. Verification and publication

- [x] 3.1 Add automated API tests for read-only route behavior, filtering, and not-found handling
- [x] 3.2 Validate the OpenSpec change, run the Python test suite, and archive the completed change
