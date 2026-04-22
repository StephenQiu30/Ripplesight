## Context

The requirements baseline for `ai-hotspot-radar` already exists, but it is distributed across product, research, engineering, acceptance, and API documents. The current repository state is strong on intent and boundaries, yet future implementation would still require engineers to manually reconcile scope, execution order, and acceptance logic before writing code.

This change converts the current document set into an OpenSpec-ready execution baseline. The design needs to preserve the existing MVP scope, align the capability split with the OpenAPI contract, and make cross-document dependencies explicit enough that later implementation can follow a spec-driven path instead of repeatedly re-analyzing the source documents.

## Goals / Non-Goals

**Goals:**
- Normalize the MVP requirements into stable OpenSpec capabilities that map cleanly to product workflows and API boundaries.
- Capture the execution path from requirements analysis to implementation planning in a way that is reviewable and repeatable.
- Surface the most important cross-document findings, constraints, and unresolved issues discovered during analysis.
- Sync the resulting execution sequencing into the product plan so planning and specification stay consistent.

**Non-Goals:**
- Implement runtime services, UI pages, or data pipelines in this change.
- Redesign the current product scope, technology choices, or source inclusion policy.
- Finalize low-level scoring formulas, storage retention policy, or exact operations dashboards that are not yet defined in the source documents.

## Decisions

### Decision: Use four capability specs as the baseline decomposition

The baseline is split into `source-governance`, `hotspot-discovery`, `digest-delivery`, and `operator-console`.

Rationale:
- This matches the functional grouping already present in the PRD.
- It mirrors the main API areas in `contracts/openapi/openapi.yaml`.
- It keeps cross-cutting concerns attached to the workflow where they matter, instead of creating a vague “miscellaneous” capability.

Alternatives considered:
- A single monolithic MVP spec: rejected because it would be difficult to review and evolve.
- A very granular per-endpoint spec split: rejected because the repository is still at baseline-definition stage and would create unnecessary churn.

### Decision: Treat the split docs as the requirements source of truth, not the archived umbrella file

The archived `docs/requirements-analysis.md` is used only as a redirect. The real baseline is derived from `PRD`, `Plan`, `Market Research`, `Tech Spec`, `Acceptance`, and the OpenAPI contract.

Rationale:
- The repository explicitly states that the old combined document is no longer maintained as the main fact source.
- Building specs from the archive entry would lose important details and create drift.

Alternatives considered:
- Reconstructing everything from the archived combined document: rejected because it is no longer authoritative.

### Decision: Encode execution sequencing both in OpenSpec tasks and in the product plan

The OpenSpec change will carry implementation-oriented tasks, and `docs/product/plan.md` will gain an OpenSpec execution section that maps those tasks back to the roadmap.

Rationale:
- Product-facing planning and engineering-facing spec execution currently live in separate places.
- Keeping both aligned reduces the chance of roadmap discussions drifting away from actual capability readiness.

Alternatives considered:
- Keeping sequencing only in `tasks.md`: rejected because product stakeholders primarily read the plan document.

### Decision: Capture requirement gaps as open questions instead of inventing missing behavior

Where the source docs set a direction but not a final rule, the baseline will preserve that ambiguity explicitly.

Rationale:
- OpenSpec should reduce ambiguity, not hide it.
- Missing details such as scoring weights or retention windows need follow-up decisions rather than fabricated certainty.

Alternatives considered:
- Filling in missing rules based on implementation preference: rejected because it would silently expand scope.

## Risks / Trade-offs

- [Capability boundaries may still shift once implementation starts] -> Keep the baseline coarse enough to evolve, and record refinements in future changes instead of overfitting now.
- [Cross-document consistency issues can be missed during manual codification] -> Validate the change with OpenSpec and keep plan/spec/API references explicit.
- [Some acceptance criteria remain qualitative rather than fully testable] -> Preserve them now, then tighten them in future changes once implementation constraints are known.
- [The OpenAPI baseline is still scaffold-level and may lag future detail] -> Treat it as the current contract source and note any mismatch as a follow-up change instead of mutating scope implicitly.

## Migration Plan

1. Create the OpenSpec change and proposal.
2. Derive capability delta specs from the current source-of-truth documents.
3. Create the task plan that defines how the baseline is synced and validated.
4. Apply the change by creating main specs under `openspec/specs/` and updating `docs/product/plan.md`.
5. Run OpenSpec validation on the change and the resulting main specs.

## Open Questions

- What exact scoring inputs and weight ranges should be used for hotspot ranking beyond the current directional rules?
- What retention period should apply to raw payloads, excerpts, and digest evidence metadata?
- What schedule, retry policy, and operational SLA should define “stable daily digest generation” in production?
- What authentication or internal access boundary, if any, is required for the operator console in MVP?
