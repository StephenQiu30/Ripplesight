## ADDED Requirements

### Requirement: Keyword CRUD

The system shall allow operators to create, list, update, delete, enable, and disable monitored keywords.

#### Scenario: Create keyword

- **WHEN** an operator submits a valid keyword
- **THEN** the system stores it in `keywords`
- **AND** returns the created keyword fields

#### Scenario: Disabled keyword skipped

- **WHEN** a keyword is disabled
- **THEN** check runs do not use it for source queries
