## ADDED Requirements

### Requirement: Analytics trend and source metrics

The system SHALL provide analytics APIs and UI for hotspot trend and source performance.

#### Scenario: Trend aggregation by period

- **WHEN** frontend requests `GET /api/analytics/trend?days=14`
- **THEN** response includes a list of date buckets
- **AND** each bucket contains total/active/filtered counts

#### Scenario: Source ranking

- **WHEN** frontend requests `GET /api/analytics/sources?days=14&limit=8`
- **THEN** response includes source ranking entries
- **AND** each entry contains total/active/filtered counts

#### Scenario: Sentiment distribution

- **WHEN** frontend requests `GET /api/analytics/sentiment?days=14`
- **THEN** response contains grouped counts by importance label
- **AND** values are non-negative integers

### Requirement: Analytics page discoverability

The workspace SHALL provide an discoverable trend-analysis route.

#### Scenario: Navigate dashboard to analytics page

- **WHEN** user opens `/app` and clicks dashboard quick action
- **THEN** system navigates to `/app/analytics`
- **AND** renders trend/source/sentiment sections
