## ADDED Requirements

### Requirement: SaaS application shell

The frontend SHALL expose a polished single-user SaaS workspace under `/app`.

#### Scenario: Workspace entry

- **WHEN** a user opens `/app`
- **THEN** they see a dashboard-style workspace
- **AND** navigation links are available for hotspots, search, keywords, sources, runs, reports, notifications, and settings

#### Scenario: Responsive shell

- **WHEN** the workspace is viewed at mobile and desktop widths
- **THEN** navigation and page content remain usable
- **AND** no primary content overlaps or creates unintended horizontal overflow
