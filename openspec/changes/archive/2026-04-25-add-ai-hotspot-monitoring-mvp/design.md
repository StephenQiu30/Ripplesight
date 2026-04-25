## Overview

Implement the MVP as a small FastAPI + Next.js system backed by PostgreSQL. The database schema is defined in `sql/001_init_schema.sql`; SQLAlchemy models mirror that schema and are used by services and routes for runtime access.

## Architecture

- FastAPI owns API routes, database initialization, database sessions, and orchestration services.
- PostgreSQL stores keywords, sources, hotspots, AI analyses, notifications, check runs, and non-sensitive settings.
- SQLAlchemy 2.0 models map to the SQL schema; application code should not scatter raw SQL beyond startup schema initialization.
- The checking pipeline reads enabled keywords and sources, fetches RSS/HN candidates, deduplicates by `(source_id, url)`, runs AI analysis or fallback, stores results, and sends SMTP notifications when configured.
- Next.js consumes FastAPI endpoints and provides operational pages for keywords, sources, hotspots, runs, notifications, and settings.

## Database Decision

`sql/001_init_schema.sql` is the table structure source of truth. The API startup path executes this file against PostgreSQL using SQLAlchemy engine access. `Base.metadata.create_all()` may exist only as a development fallback and must not become the main schema management path.

## Failure Handling

- Missing SMTP config records skipped notifications without failing the check run.
- Missing AI config or failed AI calls are recorded in check run status and use a local fallback analysis.
- A failed source increments failure count and does not stop other sources.
- Duplicate hotspots are ignored or updated using the unique `(source_id, url)` constraint.

## Non-Goals

- No Alembic or migration workflow.
- No old schema/data compatibility.
- No Celery, Redis, auth, multi-tenant support, billing, vector database, or complex workflow engine in P0.
