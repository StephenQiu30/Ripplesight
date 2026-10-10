"""Ground structure quotes against the fixed original portions sent to the model.

Adapted from AIHOT 9acad0c editorial/analyze.ts; provenance and MIT license in
LICENSE. Ripplesight records field-level discard reasons in the original
stage/result JSONB, without logging rejected material.
"""

from typing import Any

from analysis.editorial_rules import ENTITIES, MAX_BODY_CHARS, normalize_tags
from analysis.editorial_schemas import EditorialMaterial, StructureDiscard, StructureOutput


def normalize_structure(
    output: dict[str, Any] | StructureOutput, material: EditorialMaterial
) -> StructureOutput:
    # Only persisted, typed stage results can carry earlier program diagnostics.
    discards = list(output.discards) if isinstance(output, StructureOutput) else []
    data = (
        output.model_dump(mode="json", by_alias=True)
        if isinstance(output, StructureOutput)
        else dict(output)
    )
    originals = (material.body or material.excerpt, material.quoted_text)
    visible = (originals[0][:MAX_BODY_CHARS], originals[1][:2000])

    def discard(field: str, reason: Any) -> None:
        discards.append(StructureDiscard(field=field, reason=reason))

    def quote(value: object, *, field: str, limit: int) -> str | None:
        if value is None and field == "fact.evidence":
            return None
        if not isinstance(value, str):
            discard(field, "invalid_type")
            return None
        if len(value) > limit:
            discard(field, "too_long")
            return None
        if not value.strip():
            discard(field, "empty")
            return None
        if "..." in value or "…" in value:
            discard(field, "ellipsis")
            return None
        if any(character in value for character in ("\n", "\r", "\u2028", "\u2029")):
            discard(field, "cross_paragraph")
            return None
        # Exact original characters, no whitespace collapsing or paragraph joining.
        if not any(value in text for text in originals):
            discard(field, "not_in_original")
            return None
        if not any(value in text for text in visible):
            discard(field, "not_in_model_input")
            return None
        return value

    scope = data.get("scope", "unknown")
    if scope not in ("single", "composite", "unknown"):
        discard("scope", "invalid_scope")
        scope = "unknown"
    fact = data.get("fact")
    if not any(text.strip() for text in visible):
        if scope != "unknown":
            discard("scope", "no_original")
        scope = "unknown"
        if fact is not None:
            discard("fact", "no_original")
        fact = None
    elif scope == "composite":
        if fact is not None:
            discard("fact", "composite")
        fact = None
    if isinstance(fact, dict):
        fact = dict(fact)
        fact["evidence"] = quote(fact.get("evidence"), field="fact.evidence", limit=600)
        raw_conditions = fact.get("conditions", [])
        conditions: list[dict[str, str]] = []
        if not isinstance(raw_conditions, list):
            discard("fact.conditions", "invalid_type")
        else:
            for index, condition in enumerate(raw_conditions):
                field = f"fact.conditions[{index}].quote"
                if not isinstance(condition, dict) or set(condition) != {"quote"}:
                    discard(field, "invalid_type")
                    continue
                grounded = quote(condition["quote"], field=field, limit=400)
                if grounded is not None:
                    if len(conditions) == 4:
                        discard(field, "too_many")
                    else:
                        conditions.append({"quote": grounded})
        fact["conditions"] = conditions
    data.update(scope=scope, fact=fact, discards=discards)
    result = StructureOutput.model_validate(data)
    result.tags = normalize_tags(result.tags)
    result.subjects = list(
        dict.fromkeys(
            subject.strip().lower()
            for subject in result.subjects
            if subject.strip().lower() in ENTITIES
        )
    )
    return result
