## Why

The project has been reset to a lightweight self-hosted MVP, but it still needs a concrete execution contract for the AI hotspot monitoring loop. This change defines the product, data, API, and console capabilities needed to move from skeleton to usable MVP.

## What Changes

- Add keyword management, source ingestion, AI analysis, hotspot management, notification delivery, check-run orchestration, and operator console capabilities.
- Use PostgreSQL as the only P0 database and SQLAlchemy 2.0 as the FastAPI data access layer.
- Store database table definitions in `sql/001_init_schema.sql` as the schema source of truth.
- Initialize empty PostgreSQL databases by executing SQL files; do not use Alembic or old schema/data migrations.
- Use RSS and Hacker News as P0 public sources, with X/Twitter left as an optional future source.

## Capabilities

### New Capabilities

- `keyword-management`: Create, update, delete, enable, and disable monitored keywords.
- `source-ingestion`: Fetch normalized hotspot candidates from enabled sources.
- `ai-analysis`: Analyze candidates with OpenAI-compatible models and record fallback status when needed.
- `hotspot-management`: Store deduplicated hotspots and expose list/detail filtering.
- `notification-delivery`: Send optional SMTP email notifications and record notification status.
- `check-run-orchestration`: Run the shared hotspot check pipeline manually or on a lightweight schedule.
- `operator-console`: Provide a Next.js console for managing and observing the MVP workflow.

### Modified Capabilities

None.

## Impact

- Affected backend: `apps/api`, `sql/`, and PostgreSQL initialization.
- Affected frontend: `apps/web` console routes and API client usage.
- Affected docs: `AGENTS.md`, `README.md`, `docs/engineering/tech-spec.md`, and `docs/plans/`.
- New runtime behavior: API startup initializes the schema from `sql/001_init_schema.sql`.
