"""Assemble permitted story peers for the analysis-owned selection gate."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.editorial_reading import (
    load_editorial_publication_inputs_in_transaction,
    load_frozen_editorial_publication_input_in_transaction,
)
from analysis.editorial_schemas import EditorialPublicationInputView
from analysis.editorial_selection import (
    EditorialSelectionCandidate,
    EditorialSelectionGate,
    decide_editorial_selection,
)
from core.config import Settings, get_settings
from events.fact_schemas import EventPublicationGrouping
from events.facts import (
    load_publication_groupings_in_transaction,
    load_selection_grouping_exempt_ids_in_transaction,
    load_selection_peer_ids_in_transaction,
)
from events.schemas import EventInput
from monitors.editorial_events import editorial_event_topic_id
from publication.publication_models import PublicationRecord, PublicationSourcePolicy
from publication.rules import is_pool_eligible, is_selectable


@dataclass(frozen=True, slots=True)
class PublicationSelectionContext:
    snapshots: dict[UUID, EditorialPublicationInputView]
    groupings: dict[UUID, EventPublicationGrouping]
    gates: dict[UUID, EditorialSelectionGate]


def load_publication_selection_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    snapshots: dict[UUID, EditorialPublicationInputView],
    now: datetime,
    visibility_overrides: dict[UUID, str] | None = None,
) -> PublicationSelectionContext:
    """Recall across pagination and sources, then revalidate every fixed peer and policy."""
    if not session.in_transaction():
        raise RuntimeError("selection requires caller transaction")
    configured = getattr(session, "info", {}).get("settings")
    settings = configured if isinstance(configured, Settings) else get_settings()
    grouping_enabled = settings.events_cluster_enabled

    def exempt(items: dict[UUID, EditorialPublicationInputView]) -> frozenset[UUID]:
        if not grouping_enabled:
            return frozenset(items)
        result = {key for key, item in items.items() if item.backfill is True}
        identities = list(items)
        for offset in range(0, len(identities), 500):
            batch = identities[offset : offset + 500]
            inputs = []
            for identity in batch:
                item = items[identity]
                structure = item.run.result.structure if item.run and item.run.result else None
                inputs.append(
                    EventInput(
                        owner_id=owner_id,
                        topic_id=editorial_event_topic_id(owner_id),
                        content_id=identity,
                        content_version_id=item.material.content_version_id,
                        source_key=item.material.source_key,
                        title=item.material.title,
                        body=None,
                        first_seen_at=item.timeline_at,
                        first_seen_basis="published"
                        if item.material.published_at
                        else "discovered",
                        matched_keywords=frozenset(),
                        observation_id=item.observation_id,
                        input_observation_ids=item.input_observation_ids,
                        editorial_scope=structure.scope if structure else "unknown",
                    )
                )
            result.update(
                load_selection_grouping_exempt_ids_in_transaction(
                    session, owner_id=owner_id, inputs=tuple(inputs), now=now
                )
            )
        return frozenset(result)

    def group(
        items: dict[UUID, EditorialPublicationInputView],
    ) -> dict[UUID, EventPublicationGrouping]:
        result = {}
        identities = list(items)
        for offset in range(0, len(identities), 500):
            batch = identities[offset : offset + 500]
            result.update(
                load_publication_groupings_in_transaction(
                    session,
                    owner_id=owner_id,
                    content_versions={key: items[key].material.content_version_id for key in batch},
                    selected_observations={key: items[key].observation_id for key in batch},
                    now=now,
                )
            )
        return result

    base_groupings = group(snapshots)
    base_exempt = exempt(snapshots)
    peers = load_selection_peer_ids_in_transaction(
        session,
        owner_id=owner_id,
        event_ids=tuple({item.event_id for item in base_groupings.values()}),
    )
    query = select(PublicationRecord).where(PublicationRecord.owner_id == owner_id)
    if not base_exempt:
        query = query.where(PublicationRecord.content_id.in_(set(peers) | set(snapshots)))
    # Without event IDs the publication records are the existing peer discovery index.
    # Recall all fixed owner records before page/source filters, never a second fact store.
    records = {row.content_id: row for row in session.scalars(query)}
    items = dict(snapshots)
    remaining = [key for key in records if key not in items]
    for offset in range(0, len(remaining), 500):
        batch = remaining[offset : offset + 500]
        legacy = load_editorial_publication_inputs_in_transaction(
            session,
            owner_id=owner_id,
            content_ids=tuple(key for key in batch if not records[key].data.get("observation_id")),
            now=now,
        )
        for identity in batch:
            row = records[identity]
            observation = row.data.get("observation_id")
            item = (
                load_frozen_editorial_publication_input_in_transaction(
                    session,
                    owner_id=owner_id,
                    content_id=identity,
                    content_version_id=row.content_version_id,
                    observation_id=UUID(observation),
                    now=now,
                )
                if observation
                else legacy.get(identity)
            )
            if item is None or item.material.content_version_id != row.content_version_id:
                continue
            if item.material.source_key != row.source_key:
                continue
            if row.data.get("editorial_run_id") != (str(item.run.id) if item.run else None):
                continue
            if row.data.get("manual_version") != (item.run.manual_version if item.run else 0):
                continue
            if observation and tuple(str(i) for i in item.input_observation_ids) != tuple(
                row.data.get("input_observation_ids", [])
            ):
                continue
            items[identity] = item
    groupings = group(items)
    grouping_exempt = exempt(items)
    policies = {
        row.source_key: row
        for row in session.scalars(
            select(PublicationSourcePolicy).where(
                PublicationSourcePolicy.owner_id == owner_id,
                PublicationSourcePolicy.source_key.in_(
                    {item.material.source_key for item in items.values()}
                ),
            )
        )
    }
    candidates = []
    for identity, item in items.items():
        result = item.run.result if item.run and item.run.status == "complete" else None
        policy = policies.get(item.material.source_key)
        record = records.get(identity)
        visibility = (visibility_overrides or {}).get(
            identity, record.override.get("visibility", "public") if record else "public"
        )
        writing = result.writing if result else None
        eligible = bool(
            policy
            and result
            and writing
            and visibility == "public"
            and item.material.published_at is not None
            and is_selectable(
                is_pool_eligible(
                    policy.configuration["participation_mode"],
                    result.relevance,
                    writing.title_zh,
                    writing.summary_zh,
                ),
                result.selected,
                item.source.tier,
            )
        )
        candidates.append(
            EditorialSelectionCandidate(
                item,
                groupings.get(identity),
                eligible,
                grouping_enabled=grouping_enabled,
                grouping_in_scope=identity not in grouping_exempt,
            )
        )
    return PublicationSelectionContext(items, groupings, decide_editorial_selection(candidates))
