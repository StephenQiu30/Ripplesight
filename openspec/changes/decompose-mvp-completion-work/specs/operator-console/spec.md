## MODIFIED Requirements

### Requirement: Operator console
The system SHALL provide a Next.js workspace for managing keywords and observing sources, hotspots, check runs, reports, notifications, settings, and immediate search.

#### Scenario: Manage keyword from console
- **WHEN** an operator creates or disables a keyword in the console
- **THEN** the console calls the FastAPI keyword endpoints
- **AND** updates the displayed keyword list

#### Scenario: Review hotspot detail
- **WHEN** an operator opens a hotspot detail page
- **THEN** the console shows source link, keyword context, AI analysis, and notification status when available

#### Scenario: Run immediate search
- **WHEN** an operator submits a query from `/app/search`
- **THEN** the console calls `/api/search`
- **AND** displays analyzed results and source errors without creating stored hotspots

#### Scenario: Manage reports
- **WHEN** an operator opens `/app/reports`
- **THEN** the console uses `/api/reports` to create, list, preview, and send reports
- **AND** does not call or display the legacy daily-report endpoint

#### Scenario: Browser acceptance
- **WHEN** a frontend implementation pass is completed
- **THEN** `/`, `/pricing`, `/app`, `/app/search`, and `/app/reports` are reviewed in a browser at desktop and mobile widths
- **AND** visible text, buttons, forms, and tables do not overlap or overflow
