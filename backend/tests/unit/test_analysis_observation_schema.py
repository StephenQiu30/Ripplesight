"""Keep persisted analysis prompt identities compatible across the pure DTO extraction."""

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from analysis.schemas import AnalysisJobScope, AnalysisPromptItem
from content.analysis_schemas import AnalysisObservationManifest

PERSISTED_SERIALIZED_MANIFEST = """{
  "comment_observations": {
    "00000000-0000-0000-0000-000000000003": "00000000-0000-0000-0000-000000000006"
  },
  "input_observation_ids": [
    "00000000-0000-0000-0000-000000000004",
    "00000000-0000-0000-0000-000000000005",
    "00000000-0000-0000-0000-000000000006",
    "00000000-0000-0000-0000-000000000007"
  ],
  "post_observations": {
    "00000000-0000-0000-0000-000000000001": "00000000-0000-0000-0000-000000000004",
    "00000000-0000-0000-0000-000000000002": "00000000-0000-0000-0000-000000000005"
  },
  "schema_version": "analysis-observations-v1"
}"""
PERSISTED_SIGNATURE = "847187370ffab666c571f6efc751ed99ca7499fa75c7d400d29de868aa5609b7"


def test_persisted_manifest_keeps_its_signature_and_original_whole_batch() -> None:
    manifest = AnalysisObservationManifest.model_validate_json(PERSISTED_SERIALIZED_MANIFEST)
    assert manifest.signature == PERSISTED_SIGNATURE
    assert manifest.model_dump(mode="json") == json.loads(PERSISTED_SERIALIZED_MANIFEST)
    # Dict insertion order is not part of the durable original Job/Annotation identity.
    reordered = manifest.model_copy(
        update={"post_observations": dict(reversed(tuple(manifest.post_observations.items())))}
    )
    assert reordered.signature == PERSISTED_SIGNATURE
    alternative = manifest.model_copy(
        update={
            "post_observations": {UUID(int=1): UUID(int=7), UUID(int=2): UUID(int=5)},
        }
    )
    assert alternative.signature != PERSISTED_SIGNATURE


def test_original_job_scope_round_trip_preserves_manifest_and_serialized_identity() -> None:
    manifest = AnalysisObservationManifest.model_validate_json(PERSISTED_SERIALIZED_MANIFEST)
    scope = AnalysisJobScope(
        topic_id=UUID(int=8),
        topic_rule_version=1,
        prompt_version="original-prompt",
        content_version_ids=(UUID(int=1), UUID(int=2)),
        prompt_items=(
            AnalysisPromptItem(
                content_id=UUID(int=9),
                content_version_id=UUID(int=1),
                title="原始冻结正文",
                comments=("原始冻结评论",),
                comment_version_ids=(UUID(int=3),),
            ),
            AnalysisPromptItem(
                content_id=UUID(int=10), content_version_id=UUID(int=2), title="另一条正文"
            ),
        ),
        input_manifest=manifest,
    )
    serialized = scope.to_job_scope()
    restored = AnalysisJobScope.from_job_scope(serialized)
    assert restored.input_manifest is not None
    assert restored.input_manifest.signature == PERSISTED_SIGNATURE
    assert restored == scope
    assert restored.to_job_scope() == serialized


@pytest.mark.parametrize(
    "change",
    ["missing_root", "duplicate_root", "overlapping_version", "unsorted", "duplicate_closure"],
)
def test_persisted_manifest_cannot_accept_an_ambiguous_or_incomplete_input_closure(
    change: str,
) -> None:
    data = json.loads(PERSISTED_SERIALIZED_MANIFEST)
    if change == "missing_root":
        data["input_observation_ids"].remove(str(UUID(int=6)))
    elif change == "duplicate_root":
        data["comment_observations"][str(UUID(int=3))] = str(UUID(int=4))
    elif change == "overlapping_version":
        data["comment_observations"] = {str(UUID(int=1)): str(UUID(int=6))}
    elif change == "unsorted":
        data["input_observation_ids"].reverse()
    else:
        data["input_observation_ids"].insert(0, str(UUID(int=4)))
    with pytest.raises(ValidationError, match="distinct exact version references"):
        AnalysisObservationManifest.model_validate(data)
