## Why

The project already has a basic hotspot monitoring loop, but it needs a clearer MVP capability set: broader information sources, AI query expansion, relevance filtering, and a unified search path.

This change defines the project-owned MVP feature loop in the current `Python + FastAPI + PostgreSQL + SQLAlchemy + Next.js` stack.

## What Changes

- Add X/Twitter, Bing, Bilibili, and Sogou-style source adapters while keeping RSS and Hacker News.
- Add AI query expansion so each keyword can produce multiple related source queries.
- Filter low-relevance hotspots using `RELEVANCE_THRESHOLD`.
- Keep low-relevance records as `filtered`, but only notify and include `active` hotspots in daily digests.
- Add a lightweight `/api/search` endpoint for immediate cross-source search.
- Update documentation and AGENTS rules to define the MVP feature boundary.

## Capabilities

### New Capabilities

- `cross-source-search`: Search multiple sources immediately for a query and return analyzed candidate results.

### Modified Capabilities

- `source-ingestion`: Add X/Twitter, Bing, Bilibili, and Sogou-style adapters.
- `ai-analysis`: Add query expansion and enforce relevance threshold semantics.
- `hotspot-management`: Mark low-relevance items as `filtered` and active items as `active`.
- `notification-delivery`: Send event notifications only for `active` hotspots.
- `daily-digest`: Include only `active` hotspots.

## Impact

- Backend services: ingestion, AI analysis, check runner, daily digest, notification, scheduler.
- API surface: new `/api/search` endpoint.
- Configuration: X/Bing API keys, relevance threshold, SMTP, daily digest flags.
- Documentation: README, AGENTS, PRD, tech spec, acceptance criteria.
