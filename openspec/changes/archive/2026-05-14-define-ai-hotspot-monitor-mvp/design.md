## Overview

This change defines the project-owned MVP behavior in the current stack. The implementation stays intentionally lightweight and adapter-driven.

## Source Adapters

All adapters return the existing `Candidate` shape. Adapter failures raise `SourceIngestionError` so the check run can continue with other sources.

- `rss`: existing RSS/Atom parsing.
- `hacker_news`: existing Firebase API adapter.
- `x_twitter`: X API v2 Recent Search using `X_API_BEARER_TOKEN`.
- `bing`: Bing Web Search API when `BING_SEARCH_API_KEY` is configured.
- `bilibili`: public search endpoint best-effort adapter.
- `sogou`: public search best-effort adapter used as the stable Sogou-style option.

## Query Expansion

Each enabled keyword is expanded before source fetching. If AI configuration exists, the model returns 2-5 related queries. If AI fails or is not configured, fallback queries are deterministic.

## Relevance Filtering

Each new hotspot is analyzed before notification. If `relevance_score >= RELEVANCE_THRESHOLD`, the hotspot is `active`; otherwise it is `filtered`.

Only `active` hotspots trigger event email and appear in daily digests.

## Cross-source Search

`POST /api/search` accepts a query and optional source types, creates a temporary keyword object in memory, fetches candidates, analyzes them, and returns results without writing hotspots.

## Non-goals

- No queue/Redis/Celery.
- No authentication/multi-user scope.
- No complex frontend work in this change.
