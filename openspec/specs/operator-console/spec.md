## Purpose

Define the operator-facing console for configuring monitoring and reviewing results.

## Requirements

### Requirement: Operator console

The system SHALL provide a Next.js console for managing keywords and observing sources, hotspots, check runs, notifications, and settings.

#### Scenario: Manage keyword from console

- **WHEN** an operator creates or disables a keyword in the console
- **THEN** the console calls the FastAPI keyword endpoints
- **AND** updates the displayed keyword list

#### Scenario: Review hotspot detail

- **WHEN** an operator opens a hotspot detail page
- **THEN** the console shows source link, keyword context, AI analysis, and notification status when available
