## 1. OpenSpec

- [x] Archive completed `add-ai-daily-digest` after syncing specs.
- [x] Create Yupi MVP migration proposal, design, specs, and tasks.

## 2. Source ingestion

- [x] Add query expansion support.
- [x] Add X/Twitter Recent Search adapter.
- [x] Add Bing Search adapter.
- [x] Add Bilibili search adapter.
- [x] Add Sogou-style search adapter.
- [x] Seed default Yupi MVP source definitions.

## 3. Relevance and notification behavior

- [x] Mark analyzed hotspots as `active` or `filtered` based on `RELEVANCE_THRESHOLD`.
- [x] Send event email only for `active` hotspots.
- [x] Include only `active` hotspots in daily digest generation.

## 4. Cross-source search API

- [x] Add request/response schemas for `/api/search`.
- [x] Implement search service using the same adapters and AI analysis.
- [x] Register `/api/search` route.

## 5. Documentation

- [x] Update AGENTS with Yupi MVP migration rules.
- [x] Update README environment variables and usage.
- [x] Update PRD, tech spec, and acceptance docs.
