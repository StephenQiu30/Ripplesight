"""Apply or clear human fields without replacing the original paid model evidence."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from analysis.editorial_rules import finalize_copy, normalize_tags
from analysis.editorial_schemas import EditorialMaterial, EditorialOverrideInput
from core.errors import ApplicationError

_FIELDS = ("selected", "title_zh", "summary_zh", "category", "reason_zh", "tags", "silent")


def apply_editorial_correction(
    *,
    material: EditorialMaterial,
    automatic: dict[str, Any] | None,
    current: dict[str, Any] | None,
    command: EditorialOverrideInput,
) -> dict[str, Any]:
    """The original audit's before value is the automatic result, including block/unknown."""
    if automatic is None:
        if command.action == "clear" or command.clear_fields:
            raise ApplicationError("invalid_editorial_input")
        automatic = {"relevance": "unknown", "selected": False}
    overrides = dict((current or {}).get("manual_overrides", {}))
    # Older stored corrections predate the explicit field map; retain their visible fields.
    if (current or {}).get("manual") and not overrides:
        writing = (current or {}).get("writing") or {}
        overrides = {
            "selected": (current or {}).get("selected", False),
            **{key: writing[key] for key in ("title_zh", "summary_zh") if key in writing},
        }
    if command.action == "clear":
        overrides = {}
    else:
        for clear_key in command.clear_fields:
            overrides.pop(clear_key, None)
        for key in _FIELDS:
            value = getattr(command, key)
            if value is not None:
                overrides[key] = value
    result = deepcopy(automatic)
    result.update(
        manual=bool(overrides),
        manual_overrides=overrides,
        tags_override=None,
        silent=False,
    )
    writing = deepcopy(result.get("writing") or {})
    if "title_zh" in overrides or "summary_zh" in overrides:
        title = overrides.get("title_zh", writing.get("title_zh", ""))
        summary = overrides.get("summary_zh", writing.get("summary_zh", ""))
        if (
            not isinstance(title, str)
            or not isinstance(summary, str)
            or not title.strip()
            or not summary.strip()
        ):
            raise ApplicationError("invalid_editorial_input")
        fixed = finalize_copy(material, title, summary)
        if fixed.identity_guard.outcome != "pass":
            raise ApplicationError("invalid_editorial_input")
        writing.update(kind="manual", **fixed.model_dump(mode="json"))
        result["writing"], result["relevance"] = writing, "pass"
    if "reason_zh" in overrides:
        if not writing:
            raise ApplicationError("invalid_editorial_input")
        writing["reason_zh"] = overrides["reason_zh"] or None
        result["writing"] = writing
    if "category" in overrides:
        structure = deepcopy(
            result.get("structure")
            or {
                "category": None,
                "tags": [],
                "subjects": [],
                "fact": None,
            }
        )
        structure["category"] = overrides["category"]
        result["structure"] = structure
    if "selected" in overrides:
        result["selected"] = overrides["selected"]
    if "tags" in overrides:
        tags = normalize_tags(overrides["tags"]) if overrides["tags"] else []
        if overrides["tags"] and not tags:
            raise ApplicationError("invalid_editorial_input")
        overrides["tags"] = tags
        result["tags_override"] = tags
    if "silent" in overrides:
        result["silent"] = overrides["silent"]
    return result
