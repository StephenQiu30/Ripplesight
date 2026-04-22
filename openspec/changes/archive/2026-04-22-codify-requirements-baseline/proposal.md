## Why

The current requirements baseline is split across PRD, execution plan, market research, technical design, acceptance criteria, and an OpenAPI contract, but it has not yet been normalized into OpenSpec capability specs that can drive implementation consistently. We need a single spec-driven baseline so future delivery can move from document interpretation to requirement execution without re-deciding scope, boundaries, or sequencing.

## What Changes

- Translate the existing source-of-truth documents into OpenSpec capability baselines aligned to the MVP scope.
- Capture requirement-level behavior for source governance, hotspot discovery, digest delivery, and console/search workflows.
- Record cross-document findings, assumptions, and execution sequencing so the implementation order is explicit and reviewable.
- Sync the resulting execution plan back into the product plan document so the product-facing roadmap and OpenSpec workflow stay aligned.

## Capabilities

### New Capabilities
- `source-governance`: Define how sources, X keywords, monitored accounts, and source-level configuration are managed within the MVP boundary.
- `hotspot-discovery`: Define the end-to-end ingestion, normalization, deduplication, clustering, scoring, and evidence preservation workflow for hotspot events.
- `digest-delivery`: Define how daily digests are assembled, summarized, traced back to evidence, and delivered through email.
- `operator-console`: Define the browsing, detail, source tracing, search, filtering, and feedback workflows exposed to internal users.

### Modified Capabilities

## Impact

- `openspec/changes/codify-requirements-baseline/`: New proposal, design, specs, and tasks for the baseline codification workflow.
- `openspec/specs/*`: New main specs created from the analyzed requirements baseline.
- [docs/product/plan.md](/Users/stephenqiu/Desktop/StephenQiu30/Video/ai-hotspot-radar/docs/product/plan.md): Updated with an OpenSpec-aligned execution plan section.
- [contracts/openapi/openapi.yaml](/Users/stephenqiu/Desktop/StephenQiu30/Video/ai-hotspot-radar/contracts/openapi/openapi.yaml): Reviewed as the current HTTP contract baseline and referenced for spec alignment.
