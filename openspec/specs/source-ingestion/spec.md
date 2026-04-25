## Purpose

Define how external sources produce normalized hotspot candidates without blocking the full check run.

## Requirements

### Requirement: Multi-source ingestion

The system SHALL fetch normalized hotspot candidates from at least RSS and Hacker News sources.

#### Scenario: Enabled source produces candidates

- **WHEN** a check run starts with an enabled source
- **THEN** the source adapter returns normalized candidate records
- **AND** each candidate includes title, URL, source, optional author, optional published time, snippet, and raw payload

#### Scenario: Source failure is isolated

- **WHEN** one source fails
- **THEN** the check run records the failure
- **AND** continues processing other enabled sources
