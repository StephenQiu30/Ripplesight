## ADDED Requirements

### Requirement: Run fullchain discovery for approved source windows
The system SHALL execute discovery using approved sources on a deterministic MVP schedule and keep execution window metadata for each item.

#### Scenario: Apply source-specific metadata during normalization
- **WHEN** approved sources are executed
- **THEN** each normalized item records source id, source type, language, and ingestion timestamp

### Requirement: Preserve multi-source evidence with provenance
The system SHALL preserve provenance for every normalized raw content item so downstream event formation can explain “where it came from”.

#### Scenario: Persist evidence lineage for item-to-event trace
- **WHEN** normalized content is created from a source item
- **THEN** the system retains URL, source type, source id, and published-at metadata

## MODIFIED Requirements

### Requirement: Normalize multi-source content into a unified raw model
The system SHALL ingest content from approved external sources and normalize it into a consistent raw content structure before downstream analysis begins.

#### Scenario: Persist normalized raw content
- **WHEN** content is fetched from a supported source
- **THEN** the system stores it as a normalized raw content item with source linkage, publication metadata, URL, excerpt, and ingestion timestamp

#### Scenario: Continue discovery when one source fails
- **WHEN** one source adapter fails during batch collection
- **THEN** the system processes remaining source outputs and marks only the failed source window as degraded

### Requirement: Deduplicate and cluster related signals into hotspot events
The system SHALL merge duplicate or related signals from multiple sources into a single hotspot event representation.

#### Scenario: Merge same-event reports
- **WHEN** multiple normalized items describe the same underlying AI event
- **THEN** the system groups them into one hotspot event and keeps a source-count field

#### Scenario: Track event observation window
- **WHEN** a hotspot event accumulates new supporting items
- **THEN** the system updates first-seen, last-seen, and source-count metadata

### Requirement: Score events using combined evidence
The system SHALL rank hotspot events using combined evidence from news, community, product, research, and X signals, and X alone MUST NOT determine the overall ranking.

#### Scenario: Mix-source scoring for MVP ranking
- **WHEN** an event has signals from multiple source types
- **THEN** the ranking score uses cross-source evidence and records source-type contributions

#### Scenario: Prevent X-only dominance
- **WHEN** an event has only X evidence but weak non-X corroboration
- **THEN** the system does not allow X-only metrics to drive top-level ranking placement

### Requirement: Preserve evidence for every hotspot result
The system SHALL keep evidence links for each hotspot event so every surfaced result can be traced back to its contributing sources.

#### Scenario: Return links for evidence trace
- **WHEN** a hotspot event is shown in digest or console
- **THEN** the event includes evidence links and supporting item metadata
