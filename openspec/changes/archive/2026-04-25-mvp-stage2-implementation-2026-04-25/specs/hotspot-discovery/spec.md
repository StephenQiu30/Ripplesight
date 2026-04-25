## ADDED Requirements

### Requirement: Execute discovery only with governance-eligible sources
The system SHALL execute discovery only against source configurations that are currently enabled for MVP operation.

#### Scenario: Skip disabled source input
- **WHEN** discovery is run with mixed enabled and disabled source configurations
- **THEN** only enabled source IDs are normalized and clustered for event discovery

#### Scenario: Continue discovery when one source fails
- **WHEN** one source adapter fails during discovery
- **THEN** the pipeline still returns discovery output from remaining eligible sources

## MODIFIED Requirements

### Requirement: Normalize multi-source content into a unified raw model
The system SHALL ingest content from approved external sources and normalize it into a consistent raw content structure before downstream analysis begins.

#### Scenario: Persist normalized raw content
- **WHEN** content is fetched from a supported source
- **THEN** the system stores it as a normalized raw content item with source linkage, publication metadata, URL, excerpt, and ingestion timestamp

#### Scenario: Preserve source-level provenance
- **WHEN** a normalized raw content item is created
- **THEN** the system retains the originating source configuration reference needed for later evidence tracing

### Requirement: Preserve evidence for every hotspot result
The system SHALL keep evidence links for each hotspot event so every surfaced result can be traced back to its contributing sources.

#### Scenario: View supporting links for an event
- **WHEN** a hotspot event is retrieved for digest generation or console display
- **THEN** the event includes the evidence links needed to inspect its source chain
