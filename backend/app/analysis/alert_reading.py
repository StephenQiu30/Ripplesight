"""M4 valid sentiment facts; never derive sentiment from event grouping or raw keywords."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.models import ContentAnnotation
from analysis.reads import annotation_inputs_readable_in_transaction
from content.alert_reading import freeze_alert_content_inputs_in_transaction
from content.analysis_schemas import AnalysisObservationManifest
from content.report_reading import report_inputs_readable_in_transaction
from content.version_inputs import observations_readable_in_transaction


@dataclass(frozen=True)
class NegativeAlertFacts:
    value: float | None
    reason: str | None
    manifest: dict[str, object]


def load_negative_alert_facts_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    topic_rule_version: int,
    start: datetime,
    end: datetime,
    now: datetime,
) -> NegativeAlertFacts:
    if not session.in_transaction() or start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("alert sentiment reads require aware caller transaction")
    rows = tuple(
        session.scalars(
            select(ContentAnnotation)
            .where(
                ContentAnnotation.owner_id == owner_id,
                ContentAnnotation.topic_id == topic_id,
                ContentAnnotation.topic_rule_version == topic_rule_version,
                ContentAnnotation.first_valid_at >= start,
                ContentAnnotation.first_valid_at < end,
            )
            .order_by(ContentAnnotation.first_valid_at.desc(), ContentAnnotation.id)
            .limit(1001)
        )
    )
    if len(rows) > 1000:
        return NegativeAlertFacts(None, "alert_input_limit", {})
    unique: dict[UUID, ContentAnnotation] = {}
    for row in rows:
        if annotation_inputs_readable_in_transaction(session, annotation=row, now=now):
            unique.setdefault(row.content_id, row)
    selected = []
    all_inputs: set[UUID] = set()
    for row in unique.values():
        version_id = row.content_version_id
        analysis_manifest = (
            AnalysisObservationManifest.model_validate(row.input_manifest)
            if row.input_manifest is not None
            else None
        )
        original = freeze_alert_content_inputs_in_transaction(
            session,
            owner_id=owner_id,
            version_ids=(version_id,),
            as_of=end,
            now=now,
            selected_observations=analysis_manifest.post_observations
            if analysis_manifest
            else None,
        ).get(version_id)
        if original is None:
            return NegativeAlertFacts(None, "alert_input_unavailable", {})
        if not start <= original.first_received_at < end:
            continue
        if (
            row.status != "annotated"
            or row.result_state != "valid"
            or row.relevant is None
            or (row.relevant and row.sentiment not in ("positive", "neutral", "negative"))
        ):
            return NegativeAlertFacts(None, "alert_sentiment_invalid", {})
        analysis_inputs = analysis_manifest.input_observation_ids if analysis_manifest else ()
        all_inputs.update((*original.observation_ids, *analysis_inputs))
        if len(all_inputs) > 2000:
            return NegativeAlertFacts(None, "alert_input_limit", {})
        selected.append(
            {
                "annotation_id": str(row.id),
                "version_id": str(version_id),
                "observation_ids": [str(i) for i in original.observation_ids],
                "analysis_input_signature": row.input_signature,
                "analysis_observation_ids": [str(i) for i in analysis_inputs],
                "prompt_version": row.prompt_version,
                "relevant": row.relevant,
                "sentiment": row.sentiment,
                "first_valid_at": row.first_valid_at.astimezone(UTC).isoformat()
                if row.first_valid_at
                else None,
            }
        )
    if not selected:
        return NegativeAlertFacts(None, "alert_sentiment_missing", {})
    manifest: dict[str, object] = {
        "metric": "negative_count",
        "topic_id": str(topic_id),
        "topic_rule_version": topic_rule_version,
        "start": start.astimezone(UTC).isoformat(),
        "end": end.astimezone(UTC).isoformat(),
        "time_basis": "first_received",
        "inputs": selected,
    }
    return NegativeAlertFacts(
        float(
            sum(item["relevant"] is True and item["sentiment"] == "negative" for item in selected)
        ),
        None,
        manifest,
    )


def negative_alert_inputs_readable_in_transaction(
    session: Session, *, owner_id: UUID, manifest: dict[str, object], now: datetime
) -> bool:
    try:
        raw = manifest["inputs"]
        if not isinstance(raw, list) or not raw or len(raw) > 1000:
            return False
        versions = []
        observations: list[UUID] = []
        for item in raw:
            if not isinstance(item, dict):
                return False
            row = session.scalar(
                select(ContentAnnotation).where(
                    ContentAnnotation.owner_id == owner_id,
                    ContentAnnotation.id == UUID(str(item["annotation_id"])),
                )
            )
            if (
                row is None
                or not annotation_inputs_readable_in_transaction(session, annotation=row, now=now)
                or row.status != "annotated"
                or row.result_state != "valid"
                or str(row.content_version_id) != item["version_id"]
                or str(row.topic_id) != manifest["topic_id"]
                or row.topic_rule_version != manifest["topic_rule_version"]
                or row.prompt_version != item["prompt_version"]
                or row.relevant != item["relevant"]
                or row.sentiment != item["sentiment"]
                or (row.first_valid_at.astimezone(UTC).isoformat() if row.first_valid_at else None)
                != item["first_valid_at"]
            ):
                return False
            if row.input_manifest is not None:
                analysis_inputs = AnalysisObservationManifest.model_validate(row.input_manifest)
                if (
                    item.get("analysis_input_signature") != row.input_signature
                    or item.get("analysis_observation_ids")
                    != [str(value) for value in analysis_inputs.input_observation_ids]
                    or str(analysis_inputs.post_observations[row.content_version_id])
                    not in item["observation_ids"]
                ):
                    return False
                observations.extend(analysis_inputs.input_observation_ids)
            elif item.get("analysis_input_signature", "legacy") != "legacy" or item.get(
                "analysis_observation_ids", []
            ):
                return False
            versions.append(row.content_version_id)
            observations.extend(UUID(str(value)) for value in item["observation_ids"])
        observations = sorted(set(observations), key=str)
        return observations_readable_in_transaction(
            session, owner_id=owner_id, observation_ids=tuple(observations), now=now
        ) and report_inputs_readable_in_transaction(
            session,
            owner_id=owner_id,
            content_version_ids=tuple(versions),
            observation_ids=tuple(observations),
            now=now,
        )
    except (KeyError, TypeError, ValueError):
        return False
