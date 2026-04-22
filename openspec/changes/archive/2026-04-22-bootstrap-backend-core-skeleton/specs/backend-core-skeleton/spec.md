## ADDED Requirements

### Requirement: Provide framework-agnostic backend core entities
The backend core SHALL define typed, framework-agnostic entities for source governance and hotspot discovery workflows.

#### Scenario: Represent source governance entities
- **WHEN** the backend core is used to model sources, keyword rules, or monitored accounts
- **THEN** those entities are represented with typed Python models rather than ad hoc dictionaries

#### Scenario: Represent hotspot discovery entities
- **WHEN** the backend core is used to model normalized content or hotspot events
- **THEN** those entities preserve the fields required for clustering, scoring, and evidence tracing

### Requirement: Orchestrate workflows through application services
The backend core SHALL provide application services that orchestrate source listing, content normalization, clustering, and scoring through repository protocols.

#### Scenario: List active governance records
- **WHEN** an application service requests enabled sources, keyword rules, or monitored accounts
- **THEN** the service returns filtered domain entities through repository abstractions

#### Scenario: Build hotspot events from normalized content
- **WHEN** the hotspot discovery workflow is invoked with raw or normalized content
- **THEN** the application layer produces hotspot events using the shared domain rules

### Requirement: Support in-memory execution for the first slice
The backend core SHALL include in-memory infrastructure adapters so the first workflow slice is executable and testable without external systems.

#### Scenario: Execute with in-memory repositories
- **WHEN** the first backend slice runs in development or tests
- **THEN** the services can execute using in-memory repository implementations

#### Scenario: Preserve replaceable infrastructure boundaries
- **WHEN** a future persistence implementation is introduced
- **THEN** it can replace the in-memory adapters without rewriting the application workflow logic

### Requirement: Provide test coverage for baseline workflow rules
The backend core SHALL include automated tests for the first source-governance and hotspot-discovery behaviors.

#### Scenario: Validate X-only ranking protection
- **WHEN** hotspot events are scored from mixed-source and X-only evidence
- **THEN** the tests verify that X-only evidence does not outrank corroborated events by default

#### Scenario: Validate deterministic clustering
- **WHEN** related raw content items are normalized and grouped
- **THEN** the tests verify that duplicate event signals collapse into one hotspot event
