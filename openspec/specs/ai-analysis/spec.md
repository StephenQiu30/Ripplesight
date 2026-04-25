## Purpose

Define how AI analysis evaluates hotspot candidates and records explainable results.

## Requirements

### Requirement: Candidate AI analysis

The system SHALL analyze selected candidates and store truthfulness, relevance, keyword mention, importance, summary, and model metadata.

#### Scenario: AI configured

- **WHEN** AI provider configuration is present
- **THEN** the system calls the OpenAI-compatible API
- **AND** stores the analysis in `ai_analyses`

#### Scenario: AI unavailable

- **WHEN** AI configuration is missing or a model call fails
- **THEN** the system records a traceable failure or fallback
- **AND** the check run can continue
