## ADDED Requirements

### Requirement: MVP readiness evidence
The project SHALL classify remaining MVP work into automated verification, real-credential verification, manual browser verification, and deferred non-goals.

#### Scenario: Automated evidence is available
- **WHEN** an implementation pass claims an MVP behavior is complete
- **THEN** the delivery summary identifies the automated command or static check that verifies it
- **AND** does not mark credential-dependent behavior as fully verified without a real configured service

#### Scenario: Credential-dependent evidence is separated
- **WHEN** a behavior depends on X/Twitter, Bing, SMTP, or an OpenAI-compatible model credential
- **THEN** the acceptance record marks it as requiring configured-service verification
- **AND** keeps local fallback or skip behavior as a separate automated check

#### Scenario: Deferred work is protected
- **WHEN** a future task proposes multi-user auth, billing, realtime push, vector search, or a complex queue platform
- **THEN** the task must be marked outside P0 unless a new product requirement explicitly promotes it

### Requirement: Chinese documentation source of truth
The project SHALL keep primary docs under `docs/` named in Chinese and keep navigation links synchronized.

#### Scenario: Docs are renamed or moved
- **WHEN** a documentation file under `docs/` is renamed or moved
- **THEN** `AGENTS.md`, `README.md`, docs navigation, and affected markdown links are updated in the same change

#### Scenario: Legacy English docs are not reintroduced
- **WHEN** a new primary product, engineering, or plan document is added under `docs/`
- **THEN** the filename uses Chinese naming
- **AND** legacy English names are not used as current source-of-truth paths

### Requirement: Credential placeholder governance
The project SHALL document every required API key, token, SMTP secret, and model credential in env files with safe placeholders before implementation depends on it.

#### Scenario: New credential-backed feature is planned
- **WHEN** a feature requires an API key, token, SMTP password, or model credential
- **THEN** `infra/env/.env.example` includes the variable with a safe placeholder comment
- **AND** local `infra/env/.env` includes the same variable name for developer configuration

#### Scenario: Optional credential is not configured
- **WHEN** a credential-backed feature is optional
- **THEN** its default env value remains empty
- **AND** placeholder text is kept in comments rather than as a non-empty fake secret

#### Scenario: User-facing setup is documented
- **WHEN** a credential-backed feature is added or changed
- **THEN** `README.md` lists the variable, whether it is required, and what the user must fill in
