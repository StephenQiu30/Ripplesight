## MODIFIED Requirements

### Requirement: Daily digest generation

The system SHALL include only active analyzed hotspots in generated daily digest content.

#### Scenario: Active-only digest

- **WHEN** the system generates a daily digest
- **THEN** the digest includes only `active` hotspots with AI analysis
- **AND** excludes `filtered` hotspots
