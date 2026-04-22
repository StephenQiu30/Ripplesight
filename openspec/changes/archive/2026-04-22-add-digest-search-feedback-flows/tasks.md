## 1. Extend the backend core

- [x] 1.1 Add digest and feedback domain models plus query helpers needed for search and feedback submission
- [x] 1.2 Add repository protocols, application services, and in-memory adapters for digest retrieval, search, and feedback persistence

## 2. Extend the API assembly

- [x] 2.1 Add digest, search, and feedback dependencies plus serializer support in `services/api`
- [x] 2.2 Add `/api/digests/today`, `/api/search`, and `/api/feedback` routes aligned with the current contract

## 3. Verify and publish the slice

- [x] 3.1 Add automated tests for digest retrieval, search matching, and feedback submission
- [x] 3.2 Validate the OpenSpec change, run the Python test suite, and archive the completed change
