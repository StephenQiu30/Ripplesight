## ADDED Requirements

### Requirement: Daily digest generation

The system shall generate one AI daily digest report for a selected date from analyzed hotspots.

#### Scenario: Generate report with hotspots

- **WHEN** an operator requests a daily digest for a date with analyzed hotspots
- **THEN** the system stores a `daily_reports` record
- **AND** the report includes a subject, summary, content, hotspot count, and selected hotspot details

#### Scenario: Generate empty report

- **WHEN** an operator requests a daily digest for a date with no analyzed hotspots
- **THEN** the system stores a `daily_reports` record with `hotspot_count` equal to `0`
- **AND** the report content clearly states that no hotspots were found

#### Scenario: Regenerate existing date

- **WHEN** a report already exists for the requested date
- **THEN** the system refreshes that report instead of inserting a duplicate date record

### Requirement: Daily digest email delivery

The system shall send a daily digest by SMTP when configured and record delivery status.

#### Scenario: SMTP configured

- **WHEN** an operator sends an existing daily digest and SMTP config exists
- **THEN** the system sends the digest email
- **AND** records a notification linked to the daily report

#### Scenario: SMTP missing

- **WHEN** an operator sends an existing daily digest and SMTP config is missing
- **THEN** the system records a skipped notification
- **AND** the API call does not fail because of missing SMTP config

### Requirement: Daily digest retrieval

The system shall expose list and detail APIs for generated daily reports.

#### Scenario: List reports

- **WHEN** an operator lists daily reports
- **THEN** the API returns reports ordered by report date descending

#### Scenario: Read report detail

- **WHEN** an operator requests one daily report by id
- **THEN** the API returns the stored subject, summary, content, status, hotspot count, and timestamps
