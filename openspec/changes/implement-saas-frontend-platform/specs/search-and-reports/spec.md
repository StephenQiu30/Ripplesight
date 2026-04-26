### Requirement: Search and reports

The workspace SHALL expose immediate search and daily/weekly reports through current backend APIs.

#### Scenario: Immediate search

- **WHEN** a user submits a query on `/app/search`
- **THEN** the frontend calls `/api/search`
- **AND** it displays results, `active/filtered` status, and source errors

#### Scenario: Reports

- **WHEN** a user opens `/app/reports`
- **THEN** they can create daily and weekly reports through `/api/reports`
- **AND** they can preview and send generated reports

#### Scenario: Old report endpoint remains absent

- **WHEN** frontend code and rendered workspace text are inspected
- **THEN** `/api/daily-reports` is absent

