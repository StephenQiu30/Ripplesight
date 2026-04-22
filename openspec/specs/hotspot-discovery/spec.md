## Purpose

Define how approved source signals are normalized, clustered, scored, and traced into hotspot events that can support digests and console workflows.

## Requirements

### Requirement: Normalize multi-source content into a unified raw model
The system SHALL ingest content from approved external sources and normalize it into a consistent raw content structure before downstream analysis begins.

#### Scenario: Persist normalized raw content
- **WHEN** content is fetched from a supported source
- **THEN** the system stores it as a normalized raw content item with source linkage, publication metadata, URL, excerpt, and ingestion timestamp

#### Scenario: Preserve source-level provenance
- **WHEN** a normalized raw content item is created
- **THEN** the system retains the originating source configuration reference needed for later evidence tracing

### Requirement: Deduplicate and cluster related signals into hotspot events
The system SHALL merge duplicate or related signals from multiple sources into a single hotspot event representation.

#### Scenario: Merge same-event reports
- **WHEN** multiple normalized items describe the same underlying AI event
- **THEN** the system groups them into one hotspot event rather than surfacing independent duplicates

#### Scenario: Track event observation window
- **WHEN** a hotspot event accumulates new supporting items
- **THEN** the system updates the event's first-seen, last-seen, and source-count metadata

### Requirement: Score events using combined evidence
The system SHALL rank hotspot events using combined evidence from news, community, product, research, and X signals, and X alone MUST NOT determine the overall ranking.

#### Scenario: Score an event with mixed evidence
- **WHEN** an event is supported by multiple approved source types
- **THEN** the system computes a unified hotspot score using cross-source evidence

#### Scenario: Prevent X-only dominance
- **WHEN** an event has strong X activity but lacks enough corroborating evidence from other approved sources
- **THEN** the system does not allow X by itself to decide the final hotspot ranking outcome

### Requirement: Preserve evidence for every hotspot result
The system SHALL keep evidence links for each hotspot event so every surfaced result can be traced back to its contributing sources.

#### Scenario: View supporting links for an event
- **WHEN** a hotspot event is retrieved for digest generation or console display
- **THEN** the event includes the evidence links needed to inspect its source chain

#### Scenario: Continue processing when one source fails
- **WHEN** one external source or adapter fails during collection
- **THEN** the system continues processing the remaining available sources instead of aborting the entire hotspot pipeline
