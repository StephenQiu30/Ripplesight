## MODIFIED Requirements

### Requirement: Multi-source ingestion
The system SHALL fetch normalized hotspot candidates from RSS, Hacker News, X/Twitter, Bing, Bilibili, and Sogou-style sources without allowing one optional source to block the full check run.

#### Scenario: Enabled source produces candidates
- **WHEN** a check run starts with an enabled source
- **THEN** the source adapter returns normalized candidate records
- **AND** each candidate includes title, URL, source, optional author, optional published time, snippet, and raw payload

#### Scenario: Source failure is isolated
- **WHEN** one source fails
- **THEN** the check run records the failure
- **AND** continues processing other enabled sources

#### Scenario: Optional credential is missing
- **WHEN** X/Twitter or Bing is enabled without its required credential
- **THEN** the source records a skipped or failed-source error for that source
- **AND** other enabled sources continue processing in the same check run

#### Scenario: Real credential verification
- **WHEN** a real X/Twitter or Bing credential is configured for acceptance
- **THEN** the source adapter is verified against the real provider
- **AND** the evidence is recorded separately from local fallback tests
