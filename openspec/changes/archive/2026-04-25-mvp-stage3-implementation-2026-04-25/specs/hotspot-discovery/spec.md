## MODIFIED Requirements

### Requirement: Deduplicate and cluster related signals into hotspot events
The system SHALL merge duplicate or related signals from multiple sources into a single hotspot event representation.

#### Scenario: Merge same-event reports
- **WHEN** multiple normalized items with slightly different wording but high title overlap describe the same underlying AI event
- **THEN** the system shall merge them into one hotspot event instead of surfacing independent duplicates

#### Scenario: Track event observation window
- **WHEN** a hotspot event accumulates new supporting items
- **THEN** the system updates the event's first-seen, last-seen, and source-count metadata

#### Scenario: Keep punctuation/word-order variants in one cluster
- **WHEN** normalized item titles differ only by punctuation, word order, or minor stop-word noise
- **THEN** the system treats them as related signals and clusters into the same event

### Requirement: Score events using combined evidence
The system SHALL rank hotspot events using combined evidence from news, community, product, research, and X signals, and X alone MUST NOT determine the overall ranking.

#### Scenario: Score an event with mixed evidence
- **WHEN** an event is supported by multiple approved source types
- **THEN** the system computes a unified hotspot score using cross-source evidence and keeps it above single-source events in ranking

#### Scenario: Prevent X-only dominance
- **WHEN** an event has strong X activity but lacks corroborating evidence from at least one other approved source
- **THEN** the system limits the influence of X-only signals in the final hotspot ranking
