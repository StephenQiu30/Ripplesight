## MODIFIED Requirements

### Requirement: Multi-source ingestion

The system SHALL support the MVP source set while isolating individual source failures.

#### Scenario: MVP source set

- **WHEN** a check run starts
- **THEN** the system can fetch normalized candidates from RSS, Hacker News, X/Twitter, Bing, Bilibili, and Sogou-style sources

#### Scenario: X token missing

- **WHEN** an enabled X/Twitter source runs without `X_API_BEARER_TOKEN`
- **THEN** the source failure is recorded
- **AND** the check run continues processing other sources

#### Scenario: Best-effort public source failure

- **WHEN** Bilibili or Sogou public search fails
- **THEN** the source failure is isolated
- **AND** other sources continue
