## ADDED Requirements

### Requirement: Assemble a worker service with scheduled digest tasks
The system SHALL provide a worker assembly that exposes the digest workflow through Celery task entrypoints and scheduled configuration.

#### Scenario: Create the worker application
- **WHEN** the worker service is loaded
- **THEN** it provides a Celery application configured with digest-related task registration and schedule metadata

#### Scenario: Trigger the daily digest workflow
- **WHEN** the scheduled digest task runs
- **THEN** it invokes backend-core digest generation and delivery orchestration rather than embedding business logic directly in the task body

### Requirement: Render deliverable digest content from hotspot events
The system SHALL transform the assembled digest data into an outbound email-ready payload.

#### Scenario: Render digest content
- **WHEN** a digest is prepared for delivery
- **THEN** the system produces a rendered subject/body payload derived from the digest highlights and event references

#### Scenario: Preserve digest identity during rendering
- **WHEN** a digest is rendered for outbound delivery
- **THEN** the rendered payload retains the digest identifier and date context needed for delivery tracking

### Requirement: Deliver digest content through a replaceable delivery gateway
The system SHALL send rendered digest content through a delivery gateway abstraction and update delivery status accordingly.

#### Scenario: Successful digest delivery
- **WHEN** the delivery gateway accepts the rendered digest email
- **THEN** the digest delivery status is updated to a delivered-like terminal state

#### Scenario: Failed digest delivery
- **WHEN** the delivery gateway raises an error during delivery
- **THEN** the system records a failed delivery state without corrupting the underlying digest record

### Requirement: Verify worker orchestration automatically
The system SHALL include automated tests for the worker assembly, digest rendering, and delivery execution path.

#### Scenario: Run worker verification
- **WHEN** the worker-related test suite runs
- **THEN** it verifies task registration, digest rendering, and delivery-state transitions
