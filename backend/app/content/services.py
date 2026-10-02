from __future__ import annotations

import hashlib
import json
import re
from base64 import b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID, uuid4, uuid5

import structlog
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from analysis.prompts import ANALYSIS_PROMPT_VERSION
from analysis.reads import (
    load_content_annotations_in_transaction,
    load_current_annotation_states_in_transaction,
)
from analysis.schemas import AnnotationResultState, ContentAnnotationReadView
from connections.schemas import (
    ConnectionEvidenceOutcome,
    PersistedReadEvidenceInput,
    SourceEntryPoint,
)
from connections.services import (
    AppliedSourcePreset,
    SourceCapabilityEvidenceService,
    load_applied_source_presets_in_transaction,
)
from content.models import (
    ContentDiscovery,
    ContentObservation,
    ContentRecord,
    ContentThread,
    ContentVersion,
    ContentVersionRelation,
    ContentVisibilityObservation,
    HotlistEntryRecord,
    HotlistSnapshot,
)
from content.schemas import (
    AnalysisCommentContentView,
    AnalysisPostAvailabilityView,
    AnalysisPostContentView,
    CollectionContentCountView,
    CollectionContentFactView,
    CollectionSnapshotFactView,
    CommentCollectionRunInput,
    ContentAnalysisTopicView,
    ContentCommentView,
    ContentDiscoveryView,
    ContentMetricView,
    ContentObservationView,
    ContentRecordDetailView,
    ContentRecordSummaryView,
    ContentRelationType,
    ContentRuleSampleView,
    ContentSamplePreviewInput,
    ContentSamplePreviewView,
    ContentTextOrigin,
    ContentTextScope,
    ContentTruncationReason,
    ContentVersionHistoryView,
    ContentVersionRelationView,
    ContentVersionView,
    ContentVisibilityBasis,
    ContentVisibilityStatus,
    ContentVisibilityView,
    EventContentInputView,
    PersistContentDocumentInput,
    PersistContentPostInput,
    RecordContentVisibilityInput,
)
from core.errors import ApplicationError
from evidence.schemas import CleanupTargetKind, CleanupTargetSpec
from evidence.services import (
    LifecycleService,
    load_readable_resource_ids,
    readable_resource_ids_query,
)
from jobs.editorial_member import load_content_job_context_for_editorial_member_in_transaction
from jobs.services import (
    ContentJobContext,
    JobService,
    RecentCommentJobTarget,
    load_content_job_context,
    load_content_job_contexts,
    load_recent_comment_job_targets_in_transaction,
)
from monitors.schemas import MonitorRuleSetView
from monitors.services import (
    ActiveTopicScan,
    MonitorScheduleService,
    evaluate_monitor_rules,
    load_content_topic_contexts_in_transaction,
    normalize_monitor_rules,
)
from sources.adapters.web_targets import normalize_web_url
from sources.contracts import SourceCapability

type Clock = Callable[[], datetime]

_RESOURCE_TYPE = "content_observation"
_ALLOWED_FIELDS = frozenset(
    {
        "object_type",
        "external_id",
        "identity_basis",
        "canonical_url",
        "author_external_id",
        "author_name",
        "post_external_id",
        "parent_comment_external_id",
        "root_comment_external_id",
        "reply_target_comment_external_id",
        "parent_relation_status",
        "published_at",
        "like_count",
        "comment_count",
        "repost_count",
        "view_count",
        "play_count",
        "danmaku_count",
        "text_scope",
        "text_origin",
        "text_origin_ref",
        "title",
        "body",
        "truncation_reason",
        "quote_target_external_id",
        "quote_target_native_scope",
        "quote_target_author_external_id",
        "repost_target_external_id",
        "repost_target_native_scope",
        "repost_target_author_external_id",
    }
)
_DOCUMENT_ALLOWED_FIELDS = frozenset(
    {
        "object_type",
        "request_url",
        "final_url",
        "published_at",
        "text_scope",
        "text_origin",
        "text_origin_ref",
        "title",
        "body",
        "truncation_reason",
    }
)
_METRIC_FIELDS = (
    "like_count",
    "comment_count",
    "repost_count",
    "view_count",
    "play_count",
    "danmaku_count",
)
_MAX_BIGINT = 9_223_372_036_854_775_807
COMMENT_OPERATION_NAMESPACE = UUID("755fda03-92d0-4fa9-afc2-cfacb6d5d0a8")
_COMMENT_REFRESH_INTERVAL = timedelta(hours=6)
_COMMENT_POST_LIFETIME = timedelta(hours=24)
_COMMENT_TOPIC_LIMIT = 20
_RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,6}))?(?:Z|[+-]\d{2}:\d{2})$"
)
_VERSION_FIELD_NAMES = frozenset(
    {
        "text_scope",
        "text_origin",
        "text_origin_ref",
        "title",
        "body",
        "truncation_reason",
        "quote_target_external_id",
        "quote_target_native_scope",
        "quote_target_author_external_id",
        "repost_target_external_id",
        "repost_target_native_scope",
        "repost_target_author_external_id",
    }
)


@dataclass(frozen=True)
class _ContentRelationValues:
    relation_type: ContentRelationType
    target_native_scope: str | None
    target_external_id: str
    target_author_external_id: str | None

    def canonical_value(self) -> dict[str, str | None]:
        return {
            "relation_type": self.relation_type.value,
            "target_native_scope": self.target_native_scope,
            "target_external_id": self.target_external_id,
            "target_author_external_id": self.target_author_external_id,
        }


@dataclass(frozen=True)
class _ContentVersionValues:
    fingerprint: bytes
    text_scope: ContentTextScope
    text_origin: ContentTextOrigin
    text_origin_ref: str | None
    title: str | None
    body: str | None
    truncation_reason: ContentTruncationReason | None
    relations: tuple[_ContentRelationValues, ...]


def _optional_identifier(fields: Mapping[str, object], name: str) -> str | None:
    value = fields.get(name)
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{name} must be an opaque non-empty identifier")
    if len(value) > 512:
        raise ValueError(f"{name} is too long")
    return value


def _optional_url(fields: Mapping[str, object], name: str = "canonical_url") -> str | None:
    value = fields.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 2048:
        raise ValueError(f"{name} must be a bounded URL")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{name} cannot contain controls")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"{name} must be an http or https URL without credentials")
    return value


def _normalized_web_url(fields: Mapping[str, object], name: str) -> str:
    value = _optional_url(fields, name)
    if value is None:
        raise ValueError(f"{name} is required")
    hostname = urlsplit(value).hostname
    assert hostname is not None
    try:
        normalized = normalize_web_url(value, allowed_hosts=frozenset({hostname}))
    except ValueError as error:
        raise ValueError(f"{name} must be a normalized public web URL") from error
    if normalized != value:
        raise ValueError(f"{name} must be normalized")
    return normalized


def _optional_datetime_with_precision(
    fields: Mapping[str, object], name: str
) -> tuple[datetime | None, int | None]:
    value = fields.get(name)
    if value is None:
        return None, None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an RFC 3339 string")
    match = _RFC3339_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"{name} must be an RFC 3339 string with at most 6 fractional digits")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an RFC 3339 string") from error
    if parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    fractional = match.group(1)
    return parsed, len(fractional) if fractional is not None else 0


def _optional_metric(fields: Mapping[str, object], name: str) -> int | None:
    value = fields.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_BIGINT:
        raise ValueError(f"{name} must be a non-negative integer or null")
    return value


def _optional_text(
    fields: Mapping[str, object],
    name: str,
    *,
    max_length: int,
) -> str | None:
    value = fields.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{name} must be non-empty and at most {max_length} characters")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value) or any(
        ord(character) == 127 for character in value
    ):
        raise ValueError(f"{name} contains unsupported control characters")
    return value


def _required_enum[EnumT: StrEnum](
    fields: Mapping[str, object],
    name: str,
    enum_type: type[EnumT],
) -> EnumT:
    value = fields.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} is required")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"{name} has an unsupported value") from error


def _optional_truncation_reason(
    fields: Mapping[str, object],
) -> ContentTruncationReason | None:
    value = fields.get("truncation_reason")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("truncation_reason has an unsupported value")
    try:
        return ContentTruncationReason(value)
    except ValueError as error:
        raise ValueError("truncation_reason has an unsupported value") from error


def _relation_values(
    fields: Mapping[str, object],
    relation_type: ContentRelationType,
) -> _ContentRelationValues | None:
    prefix = relation_type.value
    external_id = _optional_identifier(fields, f"{prefix}_target_external_id")
    native_scope = _optional_identifier(fields, f"{prefix}_target_native_scope")
    author_external_id = _optional_identifier(fields, f"{prefix}_target_author_external_id")
    if external_id is None:
        if native_scope is not None or author_external_id is not None:
            raise ValueError(f"{prefix} target identity requires an external_id")
        return None
    return _ContentRelationValues(
        relation_type=relation_type,
        target_native_scope=native_scope,
        target_external_id=external_id,
        target_author_external_id=author_external_id,
    )


def _content_version_values(fields: Mapping[str, object]) -> _ContentVersionValues | None:
    if not any(fields.get(name) is not None for name in _VERSION_FIELD_NAMES):
        return None
    text_scope = _required_enum(fields, "text_scope", ContentTextScope)
    text_origin = _required_enum(fields, "text_origin", ContentTextOrigin)
    text_origin_ref = _optional_identifier(fields, "text_origin_ref")
    title = _optional_text(fields, "title", max_length=2_000)
    body = _optional_text(fields, "body", max_length=100_000)
    truncation_reason = _optional_truncation_reason(fields)
    relations = tuple(
        relation
        for relation_type in (ContentRelationType.QUOTE, ContentRelationType.REPOST)
        if (relation := _relation_values(fields, relation_type)) is not None
    )

    if text_origin is ContentTextOrigin.SOURCE and text_origin_ref is not None:
        raise ValueError("source text cannot declare a machine extraction reference")
    if text_origin is ContentTextOrigin.MACHINE_EXTRACTED and text_origin_ref is None:
        raise ValueError("machine-extracted text requires text_origin_ref")
    if text_scope is ContentTextScope.MEDIA_ONLY:
        if title is not None or body is not None:
            raise ValueError("media-only content cannot contain invented title or body text")
        if text_origin is not ContentTextOrigin.SOURCE:
            raise ValueError("media-only content must describe the source observation")
    elif title is None and body is None:
        raise ValueError("text content requires a title or body")
    if text_scope is ContentTextScope.TRUNCATED:
        if truncation_reason is None:
            raise ValueError("truncated text requires truncation_reason")
    elif truncation_reason is not None:
        raise ValueError("truncation_reason is only valid for truncated text")

    canonical = {
        "text_scope": text_scope.value,
        "text_origin": text_origin.value,
        "text_origin_ref": text_origin_ref,
        "title": title,
        "body": body,
        "truncation_reason": truncation_reason.value if truncation_reason else None,
        "relations": [relation.canonical_value() for relation in relations],
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).digest()
    return _ContentVersionValues(
        fingerprint=fingerprint,
        text_scope=text_scope,
        text_origin=text_origin,
        text_origin_ref=text_origin_ref,
        title=title,
        body=body,
        truncation_reason=truncation_reason,
        relations=relations,
    )


def _content_search_terms(query: str | None) -> tuple[str, ...]:
    if query is None:
        return ()
    if len(query) > 200 or "\x00" in query:
        raise ApplicationError("invalid_content_filter")
    terms = query.lower().split()
    if len(terms) > 6:
        raise ApplicationError("invalid_content_filter")
    return tuple(sorted(set(terms)))


class ContentService:
    def __init__(self, session: Session, *, clock: Clock | None = None) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    def preview_rule_samples(
        self, *, owner_id: UUID, command: ContentSamplePreviewInput
    ) -> ContentSamplePreviewView:
        rules = normalize_monitor_rules(
            match_any=command.match_any, match_all=command.match_all, exclude=command.exclude
        )
        now = self._clock()
        starts_at = now - timedelta(days=7)
        source_keys = list(dict.fromkeys(command.source_keys))
        self._session.rollback()
        with self._session.begin():
            statement = (
                select(
                    ContentRecord.id.label("content_id"),
                    ContentRecord.source_key,
                    ContentObservation.id.label("observation_id"),
                    ContentVersion.id.label("content_version_id"),
                    ContentObservation.published_at,
                    ContentObservation.observed_at,
                    ContentObservation.received_at,
                    ContentVersion.title,
                    ContentVersion.body,
                    func.row_number()
                    .over(
                        partition_by=ContentRecord.id,
                        order_by=(
                            ContentObservation.observed_at.desc(),
                            ContentObservation.received_at.desc(),
                            ContentObservation.id.desc(),
                        ),
                    )
                    .label("position"),
                )
                .join(
                    ContentObservation,
                    and_(
                        ContentObservation.owner_id == ContentRecord.owner_id,
                        ContentObservation.content_id == ContentRecord.id,
                    ),
                )
                .join(
                    ContentVersion,
                    and_(
                        ContentVersion.owner_id == ContentObservation.owner_id,
                        ContentVersion.content_id == ContentObservation.content_id,
                        ContentVersion.id == ContentObservation.content_version_id,
                    ),
                )
                .where(
                    ContentRecord.owner_id == owner_id,
                    ContentRecord.object_type.in_(("post", "webpage")),
                    ContentObservation.observed_at >= starts_at,
                    ContentObservation.observed_at < now,
                    ContentObservation.received_at <= now,
                    ContentObservation.id.in_(
                        readable_resource_ids_query(
                            owner_id=owner_id, resource_type=_RESOURCE_TYPE, now=now
                        )
                    ),
                    or_(ContentVersion.title.is_not(None), ContentVersion.body.is_not(None)),
                )
            )
            if source_keys:
                statement = statement.where(ContentRecord.source_key.in_(source_keys))
            candidates = statement.subquery()
            rows = self._session.execute(
                select(candidates)
                .where(candidates.c.position == 1)
                .order_by(
                    candidates.c.observed_at.desc(),
                    candidates.c.received_at.desc(),
                    candidates.c.observation_id.desc(),
                )
                .limit(21)
            ).all()
            samples = []
            for row in rows[:20]:
                result = evaluate_monitor_rules(
                    rules, "\n".join(part for part in (row.title, row.body) if part)
                )
                samples.append(
                    ContentRuleSampleView(
                        content_id=row.content_id,
                        observation_id=row.observation_id,
                        content_version_id=row.content_version_id,
                        source_key=row.source_key,
                        title=row.title[:300] if row.title else None,
                        body_excerpt=row.body[:1200] if row.body else None,
                        excerpt_truncated=len(row.title or "") > 300 or len(row.body or "") > 1200,
                        published_at=row.published_at,
                        observed_at=row.observed_at,
                        matched=result.matched,
                        matched_any=list(result.matched_any),
                        matched_all=list(result.matched_all),
                        excluded_by=list(result.excluded_by),
                    )
                )
            return ContentSamplePreviewView(
                rules=MonitorRuleSetView(
                    match_any=list(rules.match_any),
                    match_all=list(rules.match_all),
                    exclude=list(rules.exclude),
                ),
                rule_basis="draft",
                source_keys=source_keys,
                starts_at=starts_at,
                ends_at=now,
                sample_limit=20,
                sample_status="available" if samples else "insufficient_samples",
                truncated=len(rows) > 20,
                samples=samples,
                external_requests=0,
                model_requests=0,
            )

    def readable_post_for_comment_run_in_transaction(
        self, *, owner_id: UUID, content_id: UUID, now: datetime
    ) -> tuple[ContentRecord, ContentVersion | None]:
        """Lock one owner-visible post while a comments Job is accepted."""
        if not self._session.in_transaction() or now.utcoffset() is None:
            raise RuntimeError("comment target lookup requires a transaction and aware time")
        post = self._session.scalar(
            select(ContentRecord)
            .where(ContentRecord.owner_id == owner_id, ContentRecord.id == content_id)
            .with_for_update()
        )
        if post is None:
            raise ApplicationError("resource_not_found")
        projected = self._readable_observations(
            owner_id=owner_id, content_ids={content_id}, now=now
        ).get(content_id)
        if projected is None:
            raise ApplicationError("resource_not_found")
        observation, _ = projected
        version = (
            self._session.get(ContentVersion, observation.content_version_id)
            if observation.content_version_id is not None
            else None
        )
        return post, version

    def collection_counts_in_transaction(
        self, *, owner_id: UUID, job_ids: tuple[UUID, ...]
    ) -> tuple[CollectionContentCountView, ...]:
        """Preserve the existing count projection for callers that do not need content IDs."""
        if not self._session.in_transaction():
            raise RuntimeError("collection count reads require the caller's transaction")
        return tuple(
            CollectionContentCountView(
                job_id=fact.job_id,
                observation_count=fact.observation_count,
                ingested_count=fact.ingested_count,
                first_ingested_count=fact.first_ingested_count,
                deduplicated_count=fact.deduplicated_count,
                content_version_ids=fact.content_version_ids,
            )
            for fact in self.collection_facts_in_transaction(owner_id=owner_id, job_ids=job_ids)
        )

    def collection_facts_in_transaction(
        self, *, owner_id: UUID, job_ids: tuple[UUID, ...]
    ) -> tuple[CollectionContentFactView, ...]:
        """Return per-Job observation facts and stable IDs in two owner-scoped reads."""
        if not self._session.in_transaction():
            raise RuntimeError("collection fact reads require the caller's transaction")
        if not job_ids:
            return ()
        observations = self._session.scalars(
            select(ContentObservation).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.job_id.in_(job_ids),
            )
        ).all()
        by_job: dict[UUID, list[ContentObservation]] = {job_id: [] for job_id in job_ids}
        for item in observations:
            by_job[item.job_id].append(item)
        candidate_ids = {item.content_id for item in observations}
        first_by_content: dict[UUID, ContentObservation] = {}
        if candidate_ids:
            history = self._session.scalars(
                select(ContentObservation).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.content_id.in_(candidate_ids),
                )
            ).all()
            for item in history:
                previous = first_by_content.get(item.content_id)
                if previous is None or (item.received_at, item.id) < (
                    previous.received_at,
                    previous.id,
                ):
                    first_by_content[item.content_id] = item
        first_ingested_by_job = {job_id: 0 for job_id in job_ids}
        for first in first_by_content.values():
            if first.job_id in first_ingested_by_job:
                first_ingested_by_job[first.job_id] += 1
        return tuple(
            CollectionContentFactView(
                job_id=job_id,
                observation_count=len(by_job[job_id]),
                ingested_count=len({item.content_id for item in by_job[job_id]}),
                first_ingested_count=first_ingested_by_job[job_id],
                deduplicated_count=len(by_job[job_id]) - first_ingested_by_job[job_id],
                content_version_ids=tuple(
                    sorted(
                        {
                            item.content_version_id
                            for item in by_job[job_id]
                            if item.content_version_id is not None
                        },
                        key=str,
                    )
                ),
                content_ids=tuple(sorted({item.content_id for item in by_job[job_id]}, key=str)),
                analysis_targets_complete=all(
                    item.content_version_id is not None for item in by_job[job_id]
                ),
            )
            for job_id in job_ids
        )

    def collection_snapshot_facts_in_transaction(
        self, *, owner_id: UUID, job_ids: tuple[UUID, ...]
    ) -> tuple[CollectionSnapshotFactView, ...]:
        """Return one observed hotlist snapshot per Job, preserving empty versus absent."""
        if not self._session.in_transaction():
            raise RuntimeError("collection snapshot reads require the caller's transaction")
        if not job_ids:
            return ()
        snapshots = self._session.scalars(
            select(HotlistSnapshot).where(
                HotlistSnapshot.owner_id == owner_id,
                HotlistSnapshot.job_id.in_(job_ids),
            )
        ).all()
        by_job = {snapshot.job_id: snapshot for snapshot in snapshots}
        return tuple(
            CollectionSnapshotFactView(
                job_id=job_id,
                snapshot_id=by_job[job_id].id if job_id in by_job else None,
                entry_count=by_job[job_id].entry_count if job_id in by_job else None,
                observed_at=(
                    by_job[job_id].observed_at.astimezone(UTC) if job_id in by_job else None
                ),
            )
            for job_id in job_ids
        )

    def require_persisted_document_result(
        self,
        *,
        owner_id: UUID,
        job_id: UUID,
        content_id: UUID,
        observation_id: UUID,
    ) -> None:
        """Verify a durable webpage checkpoint before completing recovered work."""
        self._session.rollback()
        with self._session.begin():
            observation = self._session.scalar(
                select(ContentObservation)
                .join(ContentRecord, ContentRecord.id == ContentObservation.content_id)
                .where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.id == observation_id,
                    ContentObservation.content_id == content_id,
                    ContentObservation.job_id == job_id,
                    ContentRecord.owner_id == owner_id,
                    ContentRecord.object_type == "webpage",
                )
            )
            discovery = self._session.scalar(
                select(ContentDiscovery.id).where(
                    ContentDiscovery.owner_id == owner_id,
                    ContentDiscovery.content_id == content_id,
                    ContentDiscovery.job_id == job_id,
                )
            )
            if observation is None or discovery is None:
                raise ApplicationError("resource_not_found")

    @staticmethod
    def _selected_version_view(
        observation: ContentObservation,
        version_views: Mapping[UUID, ContentVersionView],
    ) -> ContentVersionView | None:
        if observation.content_version_id is None:
            return None
        return version_views.get(observation.content_version_id)

    def persist_post(
        self,
        *,
        owner_id: UUID,
        command: PersistContentPostInput,
    ) -> ContentRecordDetailView:
        self._session.rollback()
        with self._session.begin():
            return self.persist_post_in_transaction(owner_id=owner_id, command=command)

    def persist_post_in_transaction(
        self,
        *,
        owner_id: UUID,
        command: PersistContentPostInput,
        representation_fingerprint: bytes | None = None,
        member_profile_id: UUID | None = None,
    ) -> ContentRecordDetailView:
        """Persist an admitted social post within the caller's page transaction."""
        now = self._clock()
        fields, external_id = self._admitted_social_fields(
            owner_id=owner_id, command=command, now=now, object_type="post"
        )
        if any(
            name in fields
            for name in (
                "post_external_id",
                "parent_comment_external_id",
                "root_comment_external_id",
                "reply_target_comment_external_id",
                "parent_relation_status",
            )
        ):
            raise ValueError("posts cannot declare comment thread fields")
        return self._persist_admitted_content_in_transaction(
            owner_id=owner_id,
            command=command,
            object_type="post",
            native_scope=command.native_scope,
            external_id=external_id,
            identity_basis=self._identity_basis(fields),
            observation_values=self._observation_values(fields),
            version_values=_content_version_values(fields),
            now=now,
            representation_fingerprint=representation_fingerprint,
            member_profile_id=member_profile_id,
        )

    def persist_comment(
        self,
        *,
        owner_id: UUID,
        command: PersistContentPostInput,
    ) -> ContentRecordDetailView:
        self._session.rollback()
        with self._session.begin():
            return self.persist_comment_in_transaction(owner_id=owner_id, command=command)

    def persist_comment_in_transaction(
        self,
        *,
        owner_id: UUID,
        command: PersistContentPostInput,
    ) -> ContentRecordDetailView:
        """Persist an admitted comment and link it to its post and parent comment.

        The post and the parent comment may arrive later than the comment, so their
        records are created as identity-only placeholders when missing.
        """
        now = self._clock()
        fields, external_id = self._admitted_social_fields(
            owner_id=owner_id, command=command, now=now, object_type="comment"
        )
        post_external_id = _optional_identifier(fields, "post_external_id")
        if post_external_id is None:
            raise ValueError("post_external_id is required for comments")
        parent_external_id = _optional_identifier(fields, "parent_comment_external_id")
        if parent_external_id == external_id:
            raise ValueError("a comment cannot be its own parent")
        root_external_id = _optional_identifier(fields, "root_comment_external_id")
        reply_target_external_id = _optional_identifier(fields, "reply_target_comment_external_id")
        relation_status = fields.get("parent_relation_status")
        if parent_external_id is None:
            if root_external_id not in {None, external_id} or reply_target_external_id is not None:
                raise ValueError("root comment has conflicting thread references")
            if relation_status not in {None, "root"}:
                raise ValueError("root comment has an invalid parent relation status")
            root_external_id = external_id
            relation_status = "root"
        elif (
            root_external_id == external_id
            or reply_target_external_id == external_id
            or relation_status not in {None, "observed", "unavailable", "unresolved"}
        ):
            raise ValueError("reply has conflicting thread references")
        else:
            relation_status = relation_status or "unresolved"
        observation_fields = {
            name: value
            for name, value in fields.items()
            if name
            not in {
                "post_external_id",
                "parent_comment_external_id",
                "root_comment_external_id",
                "reply_target_comment_external_id",
                "parent_relation_status",
            }
        }
        saved = self._persist_admitted_content_in_transaction(
            owner_id=owner_id,
            command=command,
            object_type="comment",
            native_scope=command.native_scope,
            external_id=external_id,
            observation_values=self._observation_values(observation_fields),
            version_values=_content_version_values(observation_fields),
            now=now,
        )
        source_key = command.admission.source_key
        post = self._find_or_create_content(
            owner_id=owner_id,
            source_key=source_key,
            object_type="post",
            native_scope=command.native_scope,
            external_id=post_external_id,
            created_at=now,
        )
        parent = (
            None
            if parent_external_id is None
            else self._find_or_create_content(
                owner_id=owner_id,
                source_key=source_key,
                object_type="comment",
                native_scope=command.native_scope,
                external_id=parent_external_id,
                created_at=now,
            )
        )
        parent_id = parent.id if parent is not None else None
        root = (
            saved
            if root_external_id == external_id
            else self._find_or_create_content(
                owner_id=owner_id,
                source_key=source_key,
                object_type="comment",
                native_scope=command.native_scope,
                external_id=root_external_id,
                created_at=now,
            )
            if root_external_id is not None
            else None
        )
        reply_target = (
            self._find_or_create_content(
                owner_id=owner_id,
                source_key=source_key,
                object_type="comment",
                native_scope=command.native_scope,
                external_id=reply_target_external_id,
                created_at=now,
            )
            if reply_target_external_id is not None
            else None
        )
        inserted = self._session.scalar(
            insert(ContentThread)
            .values(
                owner_id=owner_id,
                content_id=saved.id,
                post_content_id=post.id,
                root_content_id=root.id if root is not None else None,
                parent_content_id=parent_id,
                reply_target_content_id=(reply_target.id if reply_target is not None else None),
                parent_relation_status=relation_status,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["owner_id", "content_id"])
            .returning(ContentThread.content_id)
        )
        if inserted is None:
            existing = self._session.get(ContentThread, (owner_id, saved.id))
            if (
                existing is None
                or existing.post_content_id != post.id
                or existing.parent_content_id != parent_id
                or (root is not None and existing.root_content_id not in {None, root.id})
                or (
                    reply_target is not None
                    and existing.reply_target_content_id not in {None, reply_target.id}
                )
            ):
                raise ValueError("comment thread conflicts with the stored thread")
            if root is not None and existing.root_content_id is None:
                existing.root_content_id = root.id
            if reply_target is not None and existing.reply_target_content_id is None:
                existing.reply_target_content_id = reply_target.id
            if relation_status == "observed" or (
                relation_status == "unavailable" and existing.parent_relation_status == "unresolved"
            ):
                existing.parent_relation_status = relation_status
        if fields.get("body") is not None:
            self._session.execute(
                update(ContentThread)
                .where(
                    ContentThread.owner_id == owner_id,
                    ContentThread.parent_content_id == saved.id,
                    ContentThread.parent_relation_status.in_(("unavailable", "unresolved")),
                )
                .values(parent_relation_status="observed")
            )
        return saved

    def _admitted_social_fields(
        self,
        *,
        owner_id: UUID,
        command: PersistContentPostInput,
        now: datetime,
        object_type: str,
    ) -> tuple[dict[str, object], str]:
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        if command.admission.owner_id != owner_id:
            raise ApplicationError("resource_not_found")
        if command.admission.collected_at > now:
            raise ValueError("collected_at cannot be in the future")
        fields: dict[str, object] = dict(command.admission.fields)
        unknown_fields = set(fields) - _ALLOWED_FIELDS
        if unknown_fields:
            raise ValueError("admitted payload contains fields outside the S01 contract")
        if fields.get("object_type", "post") != object_type:
            raise ValueError(f"expected a {object_type} object")
        external_id = _optional_identifier(fields, "external_id")
        if external_id is None:
            raise ValueError("external_id is required")
        return fields, external_id

    def persist_document_in_transaction(
        self,
        *,
        owner_id: UUID,
        command: PersistContentDocumentInput,
    ) -> ContentRecordDetailView:
        """Persist one normalized document inside an existing outer transaction."""
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        if command.admission.owner_id != owner_id:
            raise ApplicationError("resource_not_found")
        if command.admission.collected_at > now:
            raise ValueError("collected_at cannot be in the future")
        fields = dict(command.admission.fields)
        if set(fields) - _DOCUMENT_ALLOWED_FIELDS:
            raise ValueError("admitted payload contains fields outside the webpage contract")
        if fields.get("object_type") != "webpage":
            raise ValueError("document persistence only accepts webpage objects")
        if fields.get("text_origin") != ContentTextOrigin.MACHINE_EXTRACTED.value:
            raise ValueError("webpage text must be machine-extracted")
        text_scope = fields.get("text_scope")
        if text_scope not in {ContentTextScope.FULL.value, ContentTextScope.TRUNCATED.value}:
            raise ValueError("webpage text_scope must be full or truncated")
        if not isinstance(fields.get("body"), str):
            raise ValueError("webpage body is required")
        if (
            text_scope == ContentTextScope.TRUNCATED.value
            and fields.get("truncation_reason") != ContentTruncationReason.COLLECTOR_LIMIT.value
        ):
            raise ValueError("truncated webpage text requires collector_limit")

        request_url = _normalized_web_url(fields, "request_url")
        final_url = _normalized_web_url(fields, "final_url")
        native_scope = urlsplit(request_url).hostname
        assert native_scope is not None
        external_id = hashlib.sha256(request_url.encode()).hexdigest()
        persistence_fields = {
            name: value
            for name, value in fields.items()
            if name not in {"object_type", "request_url", "final_url"}
        }
        persistence_fields["canonical_url"] = request_url
        persistence_fields["final_url"] = final_url
        observation_values = self._observation_values(persistence_fields)
        version_values = _content_version_values(persistence_fields)
        if version_values is None:
            raise ValueError("webpage content version is required")
        return self._persist_admitted_content_in_transaction(
            owner_id=owner_id,
            command=command,
            object_type="webpage",
            native_scope=native_scope,
            external_id=external_id,
            observation_values=observation_values,
            version_values=version_values,
            now=now,
        )

    def _persist_admitted_content_in_transaction(
        self,
        *,
        owner_id: UUID,
        command: PersistContentPostInput | PersistContentDocumentInput,
        object_type: str,
        native_scope: str | None,
        external_id: str,
        observation_values: dict[str, object],
        version_values: _ContentVersionValues | None,
        now: datetime,
        identity_basis: str | None = None,
        representation_fingerprint: bytes | None = None,
        member_profile_id: UUID | None = None,
    ) -> ContentRecordDetailView:
        if representation_fingerprint is not None:
            if len(representation_fingerprint) != 32 or version_values is None:
                raise ValueError("representation fingerprint requires a version and SHA-256")
            version_values = replace(
                version_values,
                fingerprint=hashlib.sha256(
                    b"content-representation-v1\x00"
                    + version_values.fingerprint
                    + representation_fingerprint
                ).digest(),
            )
        job = (
            load_content_job_context_for_editorial_member_in_transaction(
                self._session,
                owner_id=owner_id,
                job_id=command.job_id,
                profile_id=member_profile_id,
            )
            if member_profile_id is not None
            else load_content_job_context(self._session, owner_id=owner_id, job_id=command.job_id)
        )
        if (
            job is None
            or job.source_key != command.admission.source_key
            or job.source_capability != command.admission.capability
        ):
            raise ApplicationError("resource_not_found")
        content = self._find_or_create_content(
            owner_id=owner_id,
            source_key=command.admission.source_key,
            object_type=object_type,
            native_scope=native_scope,
            external_id=external_id,
            created_at=now,
            identity_basis=identity_basis,
        )
        content_version = self._find_or_create_content_version(
            owner_id=owner_id,
            content_id=content.id,
            values=version_values,
            created_at=now,
        )
        observation_values["content_version_id"] = content_version.id if content_version else None
        observation = self._find_or_create_observation(
            owner_id=owner_id,
            content_id=content.id,
            job_id=job.job_id,
            source_operation_id=command.source_operation_id,
            observed_at=command.admission.collected_at,
            received_at=now,
            values=observation_values,
        )
        self._find_or_create_visibility_observation(
            owner_id=owner_id,
            content_id=content.id,
            job_id=job.job_id,
            source_operation_id=command.source_operation_id,
            observed_at=observation.observed_at,
            received_at=observation.received_at,
            status=ContentVisibilityStatus.VISIBLE,
            basis=ContentVisibilityBasis.CONTENT_RETURNED,
        )
        self._find_or_create_discovery(
            owner_id=owner_id,
            content_id=content.id,
            job_id=job.job_id,
            first_observed_at=observation.observed_at,
            created_at=now,
        )
        LifecycleService(self._session, clock=self._clock).track_resource_in_transaction(
            owner_id=owner_id,
            resource_type=_RESOURCE_TYPE,
            resource_id=observation.id,
            admission=command.admission,
            cleanup_targets=[
                CleanupTargetSpec(
                    kind=CleanupTargetKind.POSTGRES_CONTENT_OBSERVATION,
                    reference=str(observation.id),
                )
            ],
        )
        SourceCapabilityEvidenceService(
            self._session,
            clock=self._clock,
        ).record_persisted_read_in_transaction(
            owner_id=owner_id,
            command=PersistedReadEvidenceInput(
                operation_id=command.source_operation_id,
                connection_id=command.connection_id,
                connection_version=command.connection_version,
                capability=command.admission.capability,
                entry_point=command.entry_point,
                outcome=ConnectionEvidenceOutcome.SUCCEEDED,
                stop_reason=None,
                resource_ref=f"content_observation:{observation.id}",
                component_name=command.component_name,
                component_version=command.component_version,
            ),
        )
        readable_observations = self._readable_observation_history(
            owner_id=owner_id,
            content_id=content.id,
            now=now,
        )
        version_views = self._content_version_views(
            owner_id=owner_id,
            content_observations=[(content, item) for item in readable_observations],
            now=now,
        )
        visibility_history = self._visibility_history(
            owner_id=owner_id,
            content_id=content.id,
        )
        return self._detail_view(
            content=content,
            observation=observation,
            content_version=self._selected_version_view(observation, version_views),
            current_visibility=(visibility_history[0] if visibility_history else None),
            discoveries=self._discoveries(owner_id, content.id, {job.job_id}),
            job_contexts={job.job_id: job},
            version_history=self._version_history(readable_observations, version_views),
            visibility_history=visibility_history,
        )

    def record_visibility(
        self,
        *,
        owner_id: UUID,
        command: RecordContentVisibilityInput,
    ) -> ContentVisibilityView:
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        if command.observed_at > now:
            raise ValueError("observed_at cannot be in the future")
        self._session.rollback()
        with self._session.begin():
            content = self._session.scalar(
                select(ContentRecord)
                .where(
                    ContentRecord.owner_id == owner_id,
                    ContentRecord.id == command.content_id,
                )
                .with_for_update()
            )
            job = load_content_job_context(
                self._session,
                owner_id=owner_id,
                job_id=command.job_id,
            )
            if content is None or job is None or job.source_key != content.source_key:
                raise ApplicationError("resource_not_found")
            visibility = self._find_or_create_visibility_observation(
                owner_id=owner_id,
                content_id=content.id,
                job_id=job.job_id,
                source_operation_id=command.source_operation_id,
                observed_at=command.observed_at,
                received_at=now,
                status=command.status,
                basis=command.basis,
            )
            return self._visibility_view(visibility)

    def get_content(self, *, owner_id: UUID, content_id: UUID) -> ContentRecordDetailView:
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            content = self._session.scalar(
                select(ContentRecord).where(
                    ContentRecord.owner_id == owner_id,
                    ContentRecord.id == content_id,
                )
            )
            if content is None:
                raise ApplicationError("resource_not_found")
            projected = self._readable_observations(
                owner_id=owner_id,
                content_ids={content.id},
                now=now,
            ).get(content.id)
            if projected is None:
                raise ApplicationError("resource_not_found")
            observation, readable_job_ids = projected
            discoveries = self._discoveries(owner_id, content.id, readable_job_ids)
            contexts = load_content_job_contexts(
                self._session,
                owner_id=owner_id,
                job_ids={item.job_id for item in discoveries},
            )
            readable_observations = self._readable_observation_history(
                owner_id=owner_id,
                content_id=content.id,
                now=now,
            )
            version_views = self._content_version_views(
                owner_id=owner_id,
                content_observations=[(content, item) for item in readable_observations],
                now=now,
            )
            visibility_history = self._visibility_history(
                owner_id=owner_id,
                content_id=content.id,
            )
            version_history = self._version_history(readable_observations, version_views)
            annotations = load_content_annotations_in_transaction(
                self._session,
                owner_id=owner_id,
                content_id=content.id,
                readable_version_ids={item.content_version.id for item in version_history},
            )
            topic_ids = {item.topic_id for item in annotations}
            topic_ids.update(
                self._hotlist_topic_ids(
                    owner_id=owner_id,
                    readable_jobs={content.id: readable_job_ids},
                ).get(content.id, set())
            )
            for discovery in discoveries:
                context = contexts.get(discovery.job_id)
                if context is not None and context.configuration_ref.startswith("topic:"):
                    try:
                        topic_ids.add(UUID(context.configuration_ref.removeprefix("topic:")))
                    except ValueError:
                        continue
            topic_contexts = load_content_topic_contexts_in_transaction(
                self._session, owner_id=owner_id, topic_ids=topic_ids
            )
            analysis_topics = [
                ContentAnalysisTopicView(
                    topic_id=topic.topic_id,
                    topic_name=topic.name,
                    current_rule_version=topic.current_version,
                )
                for topic in sorted(
                    topic_contexts.values(), key=lambda item: (item.name, item.topic_id)
                )
            ]
            return self._detail_view(
                content=content,
                observation=observation,
                content_version=self._selected_version_view(observation, version_views),
                current_visibility=(visibility_history[0] if visibility_history else None),
                discoveries=discoveries,
                job_contexts=contexts,
                version_history=version_history,
                visibility_history=visibility_history,
                analysis_topics=analysis_topics,
                annotations=annotations,
            )

    def list_contents(
        self,
        *,
        owner_id: UUID,
        cursor: str | None,
        limit: int,
        topic_id: UUID | None = None,
        source_key: str | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        analysis_state: str | None = None,
        q: str | None = None,
    ) -> tuple[list[ContentRecordSummaryView], str | None]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        search_terms = _content_search_terms(q)
        if (
            (starts_at is None) != (ends_at is None)
            or (
                starts_at is not None
                and ends_at is not None
                and (
                    starts_at.utcoffset() is None
                    or ends_at.utcoffset() is None
                    or not starts_at < ends_at <= starts_at + timedelta(days=31)
                )
            )
            or (analysis_state is not None and topic_id is None)
        ):
            raise ApplicationError("invalid_content_filter")
        filter_scope: dict[str, object] = {
            "owner_id": str(owner_id),
            "topic_id": str(topic_id) if topic_id else None,
            "source_key": source_key,
            "starts_at": starts_at.astimezone(UTC).isoformat() if starts_at else None,
            "ends_at": ends_at.astimezone(UTC).isoformat() if ends_at else None,
            "analysis_state": analysis_state,
        }
        if search_terms:
            filter_scope["search_terms"] = search_terms
        fingerprint = hashlib.sha256(
            json.dumps(
                filter_scope,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:24]
        scan_cursor: UUID | None = None
        if cursor is not None:
            try:
                decoded = json.loads(
                    b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
                )
                if (
                    not isinstance(decoded, dict)
                    or decoded.get("v") != 1
                    or decoded.get("filter") != fingerprint
                ):
                    raise ValueError("cursor scope mismatch")
                scan_cursor = UUID(decoded["id"])
            except (
                Base64Error,
                UnicodeDecodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                raise ApplicationError("invalid_content_cursor") from error
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            topic_context = None
            if topic_id is not None:
                topic_context = load_content_topic_contexts_in_transaction(
                    self._session, owner_id=owner_id, topic_ids={topic_id}
                ).get(topic_id)
                if topic_context is None:
                    raise ApplicationError("resource_not_found")
            visible: list[
                tuple[
                    ContentRecord,
                    ContentObservation,
                    list[ContentDiscovery],
                    str | None,
                    bool | None,
                ]
            ] = []
            batch_size = max(50, limit * 2)
            while len(visible) <= limit:
                statement = (
                    select(ContentRecord)
                    .where(ContentRecord.owner_id == owner_id)
                    .order_by(ContentRecord.id)
                    .limit(batch_size)
                )
                if source_key is not None:
                    statement = statement.where(ContentRecord.source_key == source_key)
                if scan_cursor is not None:
                    statement = statement.where(ContentRecord.id > scan_cursor)
                records = list(self._session.scalars(statement).all())
                if not records:
                    break
                scan_cursor = records[-1].id
                projections = self._readable_observations(
                    owner_id=owner_id,
                    content_ids={record.id for record in records},
                    now=now,
                )
                matched_version_ids: set[UUID] = set()
                if search_terms:
                    search_statement = select(ContentVersion.id).where(
                        ContentVersion.owner_id == owner_id,
                        ContentVersion.id.in_(
                            {
                                observation.content_version_id
                                for observation, _ in projections.values()
                                if observation.content_version_id is not None
                            }
                        ),
                    )
                    for term in search_terms:
                        search_statement = search_statement.where(
                            or_(
                                func.lower(ContentVersion.title).contains(term, autoescape=True),
                                func.lower(ContentVersion.body).contains(term, autoescape=True),
                            )
                        )
                    matched_version_ids = set(self._session.scalars(search_statement).all())
                discoveries = self._readable_discoveries(
                    owner_id=owner_id,
                    readable_jobs={content_id: item[1] for content_id, item in projections.items()},
                )
                topic_job_ids: set[UUID] = set()
                if topic_id is not None:
                    topic_job_ids = {
                        discovery.job_id for items in discoveries.values() for discovery in items
                    }
                contexts = load_content_job_contexts(
                    self._session, owner_id=owner_id, job_ids=topic_job_ids
                )
                hotlist_topics = (
                    self._hotlist_topic_ids(
                        owner_id=owner_id,
                        readable_jobs={
                            content_id: item[1] for content_id, item in projections.items()
                        },
                    )
                    if topic_id is not None
                    else {}
                )
                annotation_states: dict[UUID, tuple[AnnotationResultState, bool | None]] = {}
                if topic_id is not None and topic_context is not None:
                    annotation_states = load_current_annotation_states_in_transaction(
                        self._session,
                        owner_id=owner_id,
                        topic_id=topic_id,
                        topic_rule_version=topic_context.current_version,
                        prompt_version=ANALYSIS_PROMPT_VERSION,
                        content_version_ids={
                            item[0].content_version_id
                            for item in projections.values()
                            if item[0].content_version_id is not None
                        },
                    )
                for record in records:
                    projection = projections.get(record.id)
                    if projection is None:
                        continue
                    observation = projection[0]
                    if search_terms and observation.content_version_id not in matched_version_ids:
                        continue
                    content_discoveries = discoveries.get(record.id, [])
                    if (
                        topic_id is not None
                        and topic_id not in hotlist_topics.get(record.id, set())
                        and not any(
                            (context := contexts.get(item.job_id)) is not None
                            and context.configuration_ref == f"topic:{topic_id}"
                            for item in content_discoveries
                        )
                    ):
                        continue
                    first_discovered_at = min(
                        (item.first_observed_at for item in content_discoveries), default=None
                    )
                    timeline_at = observation.published_at or first_discovered_at
                    if (
                        starts_at is not None
                        and ends_at is not None
                        and (timeline_at is None or not starts_at <= timeline_at < ends_at)
                    ):
                        continue
                    result = (
                        annotation_states.get(observation.content_version_id)
                        if observation.content_version_id is not None
                        else None
                    )
                    current_state = str(result[0]) if result is not None else "missing"
                    if analysis_state is not None and current_state != analysis_state:
                        continue
                    visible.append(
                        (
                            record,
                            observation,
                            content_discoveries,
                            current_state if topic_id is not None else None,
                            result[1] if result is not None else None,
                        )
                    )
                if len(records) < batch_size:
                    break
            has_more = len(visible) > limit
            page = visible[:limit]
            version_views = self._content_version_views(
                owner_id=owner_id,
                content_observations=[
                    (content, observation) for content, observation, _, _, _ in page
                ],
                now=now,
            )
            current_visibility = self._current_visibility_views(
                owner_id=owner_id,
                content_ids={content.id for content, _, _, _, _ in page},
            )
            items = [
                self._summary_view(
                    content=content,
                    observation=observation,
                    content_version=self._selected_version_view(observation, version_views),
                    current_visibility=current_visibility.get(content.id),
                    discovery_count=len(content_discoveries),
                    first_discovered_at=min(
                        (item.first_observed_at for item in content_discoveries), default=None
                    ),
                    analysis_state=current_state,
                    analysis_relevant=relevant,
                )
                for content, observation, content_discoveries, current_state, relevant in page
            ]
            next_cursor = (
                urlsafe_b64encode(
                    json.dumps(
                        {"v": 1, "id": str(page[-1][0].id), "filter": fingerprint},
                        separators=(",", ":"),
                    ).encode()
                )
                .decode()
                .rstrip("=")
                if has_more
                else None
            )
        return items, next_cursor

    def list_comments(
        self,
        *,
        owner_id: UUID,
        post_content_id: UUID,
        root_id: UUID | None,
        parent_id: UUID | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[list[ContentCommentView], str | None]:
        if root_id is not None and parent_id is not None:
            raise ApplicationError("invalid_comment_scope")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        now = self._clock()
        self._session.rollback()
        with self._session.begin():
            post = self._session.scalar(
                select(ContentRecord).where(
                    ContentRecord.owner_id == owner_id,
                    ContentRecord.id == post_content_id,
                    ContentRecord.object_type == "post",
                )
            )
            if post is None or post_content_id not in self._readable_observations(
                owner_id=owner_id, content_ids={post_content_id}, now=now
            ):
                raise ApplicationError("resource_not_found")

            threads = list(
                self._session.scalars(
                    select(ContentThread)
                    .where(
                        ContentThread.owner_id == owner_id,
                        ContentThread.post_content_id == post_content_id,
                    )
                    .order_by(ContentThread.created_at, ContentThread.content_id)
                ).all()
            )
            thread_by_id = {thread.content_id: thread for thread in threads}

            def resolve_root(thread: ContentThread) -> UUID:
                if thread.root_content_id is not None:
                    return thread.root_content_id
                visited = {thread.content_id}
                current = thread
                while current.parent_content_id is not None:
                    parent = current.parent_content_id
                    if parent in visited:
                        return parent
                    visited.add(parent)
                    ancestor = thread_by_id.get(parent)
                    if ancestor is None:
                        return parent
                    if ancestor.root_content_id is not None:
                        return ancestor.root_content_id
                    current = ancestor
                return current.content_id

            groups: dict[UUID, list[ContentThread]] = {}
            for thread in threads:
                groups.setdefault(resolve_root(thread), []).append(thread)
            root_ids = set(groups)
            candidate_ids = {thread.content_id for thread in threads} | root_ids
            readable = self._readable_observations(
                owner_id=owner_id, content_ids=candidate_ids, now=now
            )

            if root_id is not None:
                if root_id not in groups or not any(
                    thread.content_id in readable for thread in groups[root_id]
                ):
                    raise ApplicationError("resource_not_found")
                candidates = [
                    thread
                    for thread in groups[root_id]
                    if thread.content_id != root_id and thread.content_id in readable
                ]
                candidates.sort(key=lambda item: (item.created_at, item.content_id))
                selected_ids = [item.content_id for item in candidates]
            elif parent_id is not None:
                if parent_id not in candidate_ids | {
                    thread.parent_content_id
                    for thread in threads
                    if thread.parent_content_id is not None
                }:
                    raise ApplicationError("resource_not_found")
                candidates = [
                    thread
                    for thread in threads
                    if thread.parent_content_id == parent_id and thread.content_id in readable
                ]
                selected_ids = [item.content_id for item in candidates]
            else:
                selected_ids = sorted(
                    (
                        item
                        for item, members in groups.items()
                        if any(member.content_id in readable for member in members)
                    ),
                    key=lambda item: (
                        min((member.created_at, member.content_id) for member in groups[item]),
                        item,
                    ),
                )

            if cursor is not None:
                try:
                    start = selected_ids.index(cursor) + 1
                except ValueError as error:
                    raise ApplicationError("invalid_comment_cursor") from error
            else:
                start = 0
            page_ids = selected_ids[start : start + limit]
            next_cursor = str(page_ids[-1]) if start + limit < len(selected_ids) else None
            records = {
                record.id: record
                for record in self._session.scalars(
                    select(ContentRecord).where(
                        ContentRecord.owner_id == owner_id,
                        ContentRecord.id.in_(page_ids),
                    )
                ).all()
            }
            version_views = self._content_version_views(
                owner_id=owner_id,
                content_observations=[
                    (records[item], readable[item][0]) for item in page_ids if item in readable
                ],
                now=now,
            )
            child_ids = {thread.parent_content_id for thread in threads}
            items: list[ContentCommentView] = []
            for item in page_ids:
                page_thread = thread_by_id.get(item)
                if root_id is None and parent_id is None:
                    root_thread = (
                        page_thread
                        if page_thread is not None and page_thread.parent_content_id is None
                        else None
                    )
                    item_root_id = item
                    relation_status = "root" if root_thread is not None else "unresolved"
                    parent_content_id = None
                    reply_target_content_id = None
                    has_replies = any(member.content_id != item for member in groups[item])
                else:
                    assert page_thread is not None
                    item_root_id = resolve_root(page_thread)
                    relation_status = page_thread.parent_relation_status
                    parent_content_id = page_thread.parent_content_id
                    reply_target_content_id = page_thread.reply_target_content_id
                    has_replies = item in child_ids
                observation = readable.get(item)
                latest = observation[0] if observation is not None else None
                items.append(
                    ContentCommentView(
                        content_id=item,
                        external_id=records[item].external_id if latest is not None else None,
                        root_content_id=item_root_id,
                        parent_content_id=parent_content_id,
                        reply_target_content_id=reply_target_content_id,
                        parent_relation_status=relation_status,
                        latest_observation=(
                            self._observation_view(
                                latest, self._selected_version_view(latest, version_views)
                            )
                            if latest is not None
                            else None
                        ),
                        has_replies=has_replies,
                    )
                )
        return items, next_cursor

    @staticmethod
    def _identity_basis(fields: Mapping[str, object]) -> str | None:
        value = fields.get("identity_basis")
        if value is None:
            return None
        if not isinstance(value, str) or value not in {"guid", "url_fallback"}:
            raise ValueError("identity_basis must be guid or url_fallback")
        return str(value)

    @staticmethod
    def _observation_values(fields: Mapping[str, object]) -> dict[str, object]:
        published_at, published_at_fractional_digits = _optional_datetime_with_precision(
            fields, "published_at"
        )
        return {
            "canonical_url": _optional_url(fields),
            "final_url": _optional_url(fields, "final_url"),
            "author_external_id": _optional_identifier(fields, "author_external_id"),
            "author_name": _optional_text(fields, "author_name", max_length=256),
            "published_at": published_at,
            "published_at_fractional_digits": published_at_fractional_digits,
            **{name: _optional_metric(fields, name) for name in _METRIC_FIELDS},
        }

    def _find_or_create_content(
        self,
        *,
        owner_id: UUID,
        source_key: str,
        object_type: str,
        native_scope: str | None,
        external_id: str,
        created_at: datetime,
        identity_basis: str | None = None,
    ) -> ContentRecord:
        content_id = uuid4()
        inserted_id = self._session.scalar(
            insert(ContentRecord)
            .values(
                id=content_id,
                owner_id=owner_id,
                source_key=source_key,
                object_type=object_type,
                native_scope=native_scope,
                external_id=external_id,
                identity_basis=identity_basis,
                created_at=created_at,
            )
            .on_conflict_do_nothing(constraint="content_records_source_identity_key")
            .returning(ContentRecord.id)
        )
        if inserted_id is not None:
            return ContentRecord(
                id=inserted_id,
                owner_id=owner_id,
                source_key=source_key,
                object_type=object_type,
                native_scope=native_scope,
                external_id=external_id,
                identity_basis=identity_basis,
                created_at=created_at,
            )
        conditions = [
            ContentRecord.owner_id == owner_id,
            ContentRecord.source_key == source_key,
            ContentRecord.object_type == object_type,
            ContentRecord.external_id == external_id,
        ]
        conditions.append(
            ContentRecord.native_scope.is_(None)
            if native_scope is None
            else ContentRecord.native_scope == native_scope
        )
        existing = self._session.scalar(select(ContentRecord).where(*conditions).with_for_update())
        if existing is None:
            raise RuntimeError("conflicting content identity is not visible")
        if identity_basis is not None:
            if existing.identity_basis is None:
                existing.identity_basis = identity_basis
            elif existing.identity_basis != identity_basis:
                raise ValueError("conflicting content identity basis")
        return existing

    def _find_or_create_content_version(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        values: _ContentVersionValues | None,
        created_at: datetime,
    ) -> ContentVersion | None:
        if values is None:
            return None
        version_id = uuid4()
        inserted_id = self._session.scalar(
            insert(ContentVersion)
            .values(
                id=version_id,
                owner_id=owner_id,
                content_id=content_id,
                fingerprint=values.fingerprint,
                text_scope=values.text_scope.value,
                text_origin=values.text_origin.value,
                text_origin_ref=values.text_origin_ref,
                title=values.title,
                body=values.body,
                truncation_reason=(
                    values.truncation_reason.value if values.truncation_reason else None
                ),
                created_at=created_at,
            )
            .on_conflict_do_nothing(constraint="content_versions_owner_content_fingerprint_key")
            .returning(ContentVersion.id)
        )
        if inserted_id is None:
            existing = self._session.scalar(
                select(ContentVersion)
                .where(
                    ContentVersion.owner_id == owner_id,
                    ContentVersion.content_id == content_id,
                    ContentVersion.fingerprint == values.fingerprint,
                )
                .with_for_update()
            )
            if existing is None:
                raise RuntimeError("conflicting content version is not visible")
            return existing

        for relation in values.relations:
            self._session.add(
                ContentVersionRelation(
                    id=uuid4(),
                    owner_id=owner_id,
                    content_version_id=inserted_id,
                    relation_type=relation.relation_type.value,
                    target_native_scope=relation.target_native_scope,
                    target_external_id=relation.target_external_id,
                    target_author_external_id=relation.target_author_external_id,
                )
            )
        self._session.flush()
        return ContentVersion(
            id=inserted_id,
            owner_id=owner_id,
            content_id=content_id,
            fingerprint=values.fingerprint,
            text_scope=values.text_scope.value,
            text_origin=values.text_origin.value,
            text_origin_ref=values.text_origin_ref,
            title=values.title,
            body=values.body,
            truncation_reason=(
                values.truncation_reason.value if values.truncation_reason else None
            ),
            created_at=created_at,
        )

    def _find_or_create_observation(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        job_id: UUID,
        source_operation_id: UUID,
        observed_at: datetime,
        received_at: datetime,
        values: Mapping[str, object],
    ) -> ContentObservation:
        observation_id = uuid4()
        inserted_id = self._session.scalar(
            insert(ContentObservation)
            .values(
                id=observation_id,
                owner_id=owner_id,
                content_id=content_id,
                job_id=job_id,
                source_operation_id=source_operation_id,
                observed_at=observed_at,
                received_at=received_at,
                **values,
            )
            .on_conflict_do_nothing(constraint="content_observations_owner_content_operation_key")
            .returning(ContentObservation.id)
        )
        if inserted_id is not None:
            return ContentObservation(
                id=inserted_id,
                owner_id=owner_id,
                content_id=content_id,
                job_id=job_id,
                source_operation_id=source_operation_id,
                observed_at=observed_at,
                received_at=received_at,
                **values,
            )
        existing = self._session.scalar(
            select(ContentObservation)
            .where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_id == content_id,
                ContentObservation.source_operation_id == source_operation_id,
            )
            .with_for_update()
        )
        if existing is None:
            raise RuntimeError("conflicting content observation is not visible")
        if not self._observation_matches(
            existing,
            job_id=job_id,
            observed_at=observed_at,
            values=values,
        ):
            raise ApplicationError("idempotency_conflict")
        return existing

    def _find_or_create_visibility_observation(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        job_id: UUID,
        source_operation_id: UUID,
        observed_at: datetime,
        received_at: datetime,
        status: ContentVisibilityStatus,
        basis: ContentVisibilityBasis,
    ) -> ContentVisibilityObservation:
        visibility_id = uuid4()
        inserted_id = self._session.scalar(
            insert(ContentVisibilityObservation)
            .values(
                id=visibility_id,
                owner_id=owner_id,
                content_id=content_id,
                job_id=job_id,
                source_operation_id=source_operation_id,
                observed_at=observed_at,
                received_at=received_at,
                status=status.value,
                basis=basis.value,
            )
            .on_conflict_do_nothing(
                constraint="content_visibility_observations_owner_content_operation_key"
            )
            .returning(ContentVisibilityObservation.id)
        )
        if inserted_id is not None:
            return ContentVisibilityObservation(
                id=inserted_id,
                owner_id=owner_id,
                content_id=content_id,
                job_id=job_id,
                source_operation_id=source_operation_id,
                observed_at=observed_at,
                received_at=received_at,
                status=status.value,
                basis=basis.value,
            )
        existing = self._session.scalar(
            select(ContentVisibilityObservation)
            .where(
                ContentVisibilityObservation.owner_id == owner_id,
                ContentVisibilityObservation.content_id == content_id,
                ContentVisibilityObservation.source_operation_id == source_operation_id,
            )
            .with_for_update()
        )
        if existing is None:
            raise RuntimeError("conflicting content visibility observation is not visible")
        if (
            existing.job_id != job_id
            or existing.observed_at != observed_at
            or existing.status != status.value
            or existing.basis != basis.value
        ):
            raise ApplicationError("idempotency_conflict")
        return existing

    def _find_or_create_discovery(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        job_id: UUID,
        first_observed_at: datetime,
        created_at: datetime,
    ) -> None:
        self._session.execute(
            insert(ContentDiscovery)
            .values(
                id=uuid4(),
                owner_id=owner_id,
                content_id=content_id,
                job_id=job_id,
                first_observed_at=first_observed_at,
                created_at=created_at,
            )
            .on_conflict_do_nothing(constraint="content_discoveries_owner_content_job_key")
        )

    @staticmethod
    def _observation_matches(
        observation: ContentObservation,
        *,
        job_id: UUID,
        observed_at: datetime,
        values: Mapping[str, object],
    ) -> bool:
        return (
            observation.job_id == job_id
            and observation.observed_at == observed_at
            and all(getattr(observation, name) == value for name, value in values.items())
        )

    def _hotlist_topic_ids(
        self,
        *,
        owner_id: UUID,
        readable_jobs: Mapping[UUID, set[UUID]],
    ) -> dict[UUID, set[UUID]]:
        if not readable_jobs:
            return {}
        rows = self._session.execute(
            select(
                HotlistEntryRecord.content_id,
                HotlistSnapshot.job_id,
                HotlistEntryRecord.matched_topic_ids,
            )
            .join(
                HotlistSnapshot,
                and_(
                    HotlistSnapshot.owner_id == HotlistEntryRecord.owner_id,
                    HotlistSnapshot.id == HotlistEntryRecord.snapshot_id,
                ),
            )
            .where(
                HotlistEntryRecord.owner_id == owner_id,
                HotlistEntryRecord.content_id.in_(readable_jobs),
            )
        ).all()
        result: dict[UUID, set[UUID]] = {}
        for content_id, job_id, topic_ids in rows:
            if job_id in readable_jobs.get(content_id, set()):
                result.setdefault(content_id, set()).update(UUID(value) for value in topic_ids)
        return result

    def _readable_observations(
        self,
        *,
        owner_id: UUID,
        content_ids: set[UUID],
        now: datetime,
    ) -> dict[UUID, tuple[ContentObservation, set[UUID]]]:
        if not content_ids:
            return {}
        observations = list(
            self._session.scalars(
                select(ContentObservation).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.content_id.in_(content_ids),
                )
            ).all()
        )
        readable_ids = load_readable_resource_ids(
            self._session,
            owner_id=owner_id,
            resource_type=_RESOURCE_TYPE,
            resource_ids={item.id for item in observations},
            now=now,
        )
        grouped: dict[UUID, list[ContentObservation]] = {}
        for observation in observations:
            if observation.id in readable_ids:
                grouped.setdefault(observation.content_id, []).append(observation)
        return {
            content_id: (
                max(items, key=lambda item: (item.observed_at, item.received_at, item.id)),
                {item.job_id for item in items},
            )
            for content_id, items in grouped.items()
        }

    def _readable_observation_history(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
        now: datetime,
    ) -> list[ContentObservation]:
        observations = list(
            self._session.scalars(
                select(ContentObservation).where(
                    ContentObservation.owner_id == owner_id,
                    ContentObservation.content_id == content_id,
                )
            ).all()
        )
        readable_ids = load_readable_resource_ids(
            self._session,
            owner_id=owner_id,
            resource_type=_RESOURCE_TYPE,
            resource_ids={item.id for item in observations},
            now=now,
        )
        return sorted(
            (item for item in observations if item.id in readable_ids),
            key=lambda item: (item.observed_at, item.received_at, item.id),
            reverse=True,
        )

    def _visibility_history(
        self,
        *,
        owner_id: UUID,
        content_id: UUID,
    ) -> list[ContentVisibilityView]:
        observations = self._session.scalars(
            select(ContentVisibilityObservation)
            .where(
                ContentVisibilityObservation.owner_id == owner_id,
                ContentVisibilityObservation.content_id == content_id,
            )
            .order_by(
                ContentVisibilityObservation.observed_at.desc(),
                ContentVisibilityObservation.received_at.desc(),
                ContentVisibilityObservation.id.desc(),
            )
        ).all()
        return [self._visibility_view(item) for item in observations]

    def _current_visibility_views(
        self,
        *,
        owner_id: UUID,
        content_ids: set[UUID],
    ) -> dict[UUID, ContentVisibilityView]:
        if not content_ids:
            return {}
        observations = self._session.scalars(
            select(ContentVisibilityObservation).where(
                ContentVisibilityObservation.owner_id == owner_id,
                ContentVisibilityObservation.content_id.in_(content_ids),
            )
        ).all()
        current: dict[UUID, ContentVisibilityObservation] = {}
        for item in observations:
            previous = current.get(item.content_id)
            if previous is None or (
                item.observed_at,
                item.received_at,
                item.id,
            ) > (
                previous.observed_at,
                previous.received_at,
                previous.id,
            ):
                current[item.content_id] = item
        return {content_id: self._visibility_view(item) for content_id, item in current.items()}

    def _discoveries(
        self,
        owner_id: UUID,
        content_id: UUID,
        readable_job_ids: set[UUID],
    ) -> list[ContentDiscovery]:
        if not readable_job_ids:
            return []
        return list(
            self._session.scalars(
                select(ContentDiscovery)
                .where(
                    ContentDiscovery.owner_id == owner_id,
                    ContentDiscovery.content_id == content_id,
                    ContentDiscovery.job_id.in_(readable_job_ids),
                )
                .order_by(ContentDiscovery.first_observed_at, ContentDiscovery.id)
            ).all()
        )

    def _readable_discoveries(
        self,
        *,
        owner_id: UUID,
        readable_jobs: dict[UUID, set[UUID]],
    ) -> dict[UUID, list[ContentDiscovery]]:
        all_job_ids = set().union(*readable_jobs.values()) if readable_jobs else set()
        if not all_job_ids:
            return {}
        rows = self._session.scalars(
            select(ContentDiscovery).where(
                ContentDiscovery.owner_id == owner_id,
                ContentDiscovery.content_id.in_(set(readable_jobs)),
                ContentDiscovery.job_id.in_(all_job_ids),
            )
        ).all()
        grouped: dict[UUID, list[ContentDiscovery]] = {}
        for row in rows:
            if row.job_id in readable_jobs[row.content_id]:
                grouped.setdefault(row.content_id, []).append(row)
        return grouped

    def _content_version_views(
        self,
        *,
        owner_id: UUID,
        content_observations: list[tuple[ContentRecord, ContentObservation]],
        now: datetime,
    ) -> dict[UUID, ContentVersionView]:
        version_ids = {
            observation.content_version_id
            for _, observation in content_observations
            if observation.content_version_id is not None
        }
        if not version_ids:
            return {}
        versions = list(
            self._session.scalars(
                select(ContentVersion).where(
                    ContentVersion.owner_id == owner_id,
                    ContentVersion.id.in_(version_ids),
                )
            ).all()
        )
        relations = list(
            self._session.scalars(
                select(ContentVersionRelation).where(
                    ContentVersionRelation.owner_id == owner_id,
                    ContentVersionRelation.content_version_id.in_(version_ids),
                )
            ).all()
        )
        content_by_id = {content.id: content for content, _ in content_observations}
        relation_version = {version.id: version for version in versions}
        target_external_ids = {relation.target_external_id for relation in relations}
        target_source_keys = {
            content_by_id[version.content_id].source_key
            for version in versions
            if version.content_id in content_by_id
        }
        target_candidates = (
            list(
                self._session.scalars(
                    select(ContentRecord).where(
                        ContentRecord.owner_id == owner_id,
                        ContentRecord.object_type == "post",
                        ContentRecord.source_key.in_(target_source_keys),
                        ContentRecord.external_id.in_(target_external_ids),
                    )
                ).all()
            )
            if target_external_ids and target_source_keys
            else []
        )
        readable_target_ids = set(
            self._readable_observations(
                owner_id=owner_id,
                content_ids={candidate.id for candidate in target_candidates},
                now=now,
            )
        )
        readable_targets = {
            (
                candidate.source_key,
                candidate.native_scope,
                candidate.external_id,
            ): candidate.id
            for candidate in target_candidates
            if candidate.id in readable_target_ids
        }
        grouped_relations: dict[UUID, list[ContentVersionRelationView]] = {}
        relation_order = {
            ContentRelationType.QUOTE.value: 0,
            ContentRelationType.REPOST.value: 1,
        }
        for relation in sorted(
            relations,
            key=lambda item: (relation_order[item.relation_type], item.id),
        ):
            version = relation_version[relation.content_version_id]
            source_key = content_by_id[version.content_id].source_key
            grouped_relations.setdefault(relation.content_version_id, []).append(
                ContentVersionRelationView(
                    relation_type=ContentRelationType(relation.relation_type),
                    target_native_scope=relation.target_native_scope,
                    target_external_id=relation.target_external_id,
                    target_author_external_id=relation.target_author_external_id,
                    target_content_id=readable_targets.get(
                        (
                            source_key,
                            relation.target_native_scope,
                            relation.target_external_id,
                        )
                    ),
                )
            )
        return {
            version.id: ContentVersionView(
                id=version.id,
                text_scope=ContentTextScope(version.text_scope),
                text_origin=ContentTextOrigin(version.text_origin),
                text_origin_ref=version.text_origin_ref,
                title=version.title,
                body=version.body,
                truncation_reason=(
                    ContentTruncationReason(version.truncation_reason)
                    if version.truncation_reason
                    else None
                ),
                relations=grouped_relations.get(version.id, []),
            )
            for version in versions
        }

    @staticmethod
    def _version_history(
        observations: list[ContentObservation],
        version_views: Mapping[UUID, ContentVersionView],
    ) -> list[ContentVersionHistoryView]:
        grouped: dict[UUID, list[datetime]] = {}
        for observation in observations:
            version_id = observation.content_version_id
            if version_id is not None and version_id in version_views:
                grouped.setdefault(version_id, []).append(observation.observed_at)
        return sorted(
            (
                ContentVersionHistoryView(
                    content_version=version_views[version_id],
                    first_observed_at=min(observed_at),
                    last_observed_at=max(observed_at),
                    observation_count=len(observed_at),
                )
                for version_id, observed_at in grouped.items()
            ),
            key=lambda item: (item.last_observed_at, item.content_version.id),
            reverse=True,
        )

    @staticmethod
    def _visibility_view(
        observation: ContentVisibilityObservation,
    ) -> ContentVisibilityView:
        return ContentVisibilityView(
            id=observation.id,
            observed_at=observation.observed_at,
            received_at=observation.received_at,
            status=ContentVisibilityStatus(observation.status),
            basis=ContentVisibilityBasis(observation.basis),
        )

    @staticmethod
    def _observation_view(
        observation: ContentObservation,
        content_version: ContentVersionView | None,
    ) -> ContentObservationView:
        return ContentObservationView(
            id=observation.id,
            observed_at=observation.observed_at,
            received_at=observation.received_at,
            published_at=observation.published_at,
            published_at_fractional_digits=observation.published_at_fractional_digits,
            canonical_url=observation.canonical_url,
            final_url=observation.final_url,
            author_external_id=observation.author_external_id,
            metrics=ContentMetricView(
                **{name: getattr(observation, name) for name in _METRIC_FIELDS}
            ),
            content_version=content_version,
        )

    @classmethod
    def _summary_view(
        cls,
        *,
        content: ContentRecord,
        observation: ContentObservation,
        content_version: ContentVersionView | None,
        current_visibility: ContentVisibilityView | None,
        discovery_count: int,
        first_discovered_at: datetime | None = None,
        analysis_state: str | None = None,
        analysis_relevant: bool | None = None,
    ) -> ContentRecordSummaryView:
        timeline_at = observation.published_at or first_discovered_at
        return ContentRecordSummaryView(
            id=content.id,
            source_key=content.source_key,
            object_type=content.object_type,
            native_scope=content.native_scope,
            external_id=content.external_id,
            identity_basis=content.identity_basis,
            latest_observation=cls._observation_view(observation, content_version),
            current_visibility=current_visibility,
            discovery_count=discovery_count,
            timeline_at=timeline_at,
            timeline_basis=(
                "published_at"
                if observation.published_at is not None
                else "first_observed_at"
                if first_discovered_at is not None
                else None
            ),
            analysis_state=analysis_state,
            analysis_relevant=analysis_relevant,
        )

    @classmethod
    def _detail_view(
        cls,
        *,
        content: ContentRecord,
        observation: ContentObservation,
        content_version: ContentVersionView | None,
        current_visibility: ContentVisibilityView | None,
        discoveries: list[ContentDiscovery],
        job_contexts: dict[UUID, ContentJobContext],
        version_history: list[ContentVersionHistoryView],
        visibility_history: list[ContentVisibilityView],
        analysis_topics: list[ContentAnalysisTopicView] | None = None,
        annotations: list[ContentAnnotationReadView] | None = None,
    ) -> ContentRecordDetailView:
        discovery_views = [
            ContentDiscoveryView(
                job_id=item.job_id,
                configuration_ref=job_contexts[item.job_id].configuration_ref,
                configuration_version=job_contexts[item.job_id].configuration_version,
                first_observed_at=item.first_observed_at,
                scan_kind=job_contexts[item.job_id].scan_kind,
            )
            for item in discoveries
            if item.job_id in job_contexts
        ]
        summary = cls._summary_view(
            content=content,
            observation=observation,
            content_version=content_version,
            current_visibility=current_visibility,
            discovery_count=len(discovery_views),
            first_discovered_at=min((item.first_observed_at for item in discoveries), default=None),
        )
        return ContentRecordDetailView(
            **summary.model_dump(),
            discoveries=discovery_views,
            version_history=version_history,
            visibility_history=visibility_history,
            analysis_topics=analysis_topics or [],
            annotations=annotations or [],
            analysis_prompt_version=ANALYSIS_PROMPT_VERSION,
        )


class ContentObservationCleanup:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def __call__(self, reference: str) -> None:
        try:
            observation_id = UUID(reference)
        except ValueError as error:
            raise ValueError("content observation cleanup reference must be a UUID") from error
        with self._sessions() as session, session.begin():
            observation = session.scalar(
                select(ContentObservation)
                .where(ContentObservation.id == observation_id)
                .with_for_update()
            )
            if observation is None:
                return
            content_id = observation.content_id
            version_id = observation.content_version_id
            session.delete(observation)
            session.flush()
            remaining_count = session.scalar(
                select(func.count(ContentObservation.id)).where(
                    ContentObservation.content_id == content_id
                )
            )
            if not remaining_count:
                content = session.get(ContentRecord, content_id)
                if content is not None:
                    session.delete(content)
                return
            if version_id is None:
                return
            version_reference_count = session.scalar(
                select(func.count(ContentObservation.id)).where(
                    ContentObservation.content_version_id == version_id
                )
            )
            if not version_reference_count:
                version = session.get(ContentVersion, version_id)
                if version is not None:
                    session.delete(version)


@dataclass(frozen=True, slots=True)
class CommentScanPost:
    owner_id: UUID
    content_id: UUID
    source_key: str
    external_id: str
    created_at: datetime
    title: str | None
    body: str | None
    like_count: int | None
    comment_count: int
    repost_count: int | None
    last_observed_at: datetime | None = None

    @property
    def interaction_score(self) -> int:
        return (self.like_count or 0) + 2 * self.comment_count + 3 * (self.repost_count or 0)

    @property
    def searchable_text(self) -> str:
        return "\n".join(item for item in (self.title, self.body) if item)


@dataclass(frozen=True, slots=True)
class CommentScanCandidate:
    post: CommentScanPost
    topic: ActiveTopicScan
    preset: AppliedSourcePreset


def comment_bucket_start(now: datetime, *, interval_seconds: int = 21_600) -> datetime:
    if now.tzinfo is None:
        raise ValueError("comment scan time must be timezone-aware")
    if not 60 <= interval_seconds <= 86_400:
        raise ValueError("comment refresh interval is out of bounds")
    now_utc = now.astimezone(UTC)
    return datetime.fromtimestamp(
        int(now_utc.timestamp()) // interval_seconds * interval_seconds, tz=UTC
    )


def comment_operation_id(
    content_id: UUID, bucket_start: datetime, *, connection_version: int | None = None
) -> UUID:
    if bucket_start.tzinfo is None:
        raise ValueError("comment bucket must be timezone-aware")
    if connection_version is not None and connection_version < 1:
        raise ValueError("comment connection version must be positive")
    bucket_text = bucket_start.astimezone(UTC).isoformat().replace("+00:00", "Z")
    name = f"comments:{content_id}:{bucket_text}"
    if connection_version is not None:
        name = f"{name}:connection:{connection_version}"
    return uuid5(COMMENT_OPERATION_NAMESPACE, name)


def _comment_collection_run(
    candidate: CommentScanCandidate,
    *,
    bucket_start: datetime,
) -> CommentCollectionRunInput:
    policy = candidate.preset.comment_scan_policy
    if candidate.post.source_key == "hackernews" and policy is None:
        raise ValueError("Hacker News comments require a versioned scan policy")
    return CommentCollectionRunInput(
        operation_id=comment_operation_id(
            candidate.post.content_id,
            bucket_start,
            connection_version=candidate.preset.connection_version,
        ),
        configuration_ref=f"topic:{candidate.topic.topic_id}",
        configuration_version=candidate.topic.topic_version,
        source_key=candidate.post.source_key,
        connection_id=candidate.preset.connection_id,
        connection_version=candidate.preset.connection_version,
        post_external_id=candidate.post.external_id,
        entry_point=SourceEntryPoint.SCHEDULED,
        starts_at=bucket_start - timedelta(seconds=policy.refresh_interval_seconds)
        if policy is not None
        else bucket_start - _COMMENT_REFRESH_INTERVAL,
        ends_at=bucket_start,
        scheduled_for_at=bucket_start,
        page_size=policy.page_size if policy is not None else 20,
        max_pages=policy.max_pages if policy is not None else 1,
        max_requests=policy.max_requests if policy is not None else 1,
        max_seconds=policy.max_seconds if policy is not None else 90,
        first_level_limit=policy.first_level_limit if policy is not None else 200,
        replies_per_thread_limit=policy.replies_per_thread_limit if policy is not None else 20,
    )


def _rank_comment_posts_for_topic(
    *,
    topic: ActiveTopicScan,
    posts: tuple[CommentScanPost, ...],
    presets: Mapping[tuple[UUID, str], AppliedSourcePreset],
    recent_jobs: frozenset[RecentCommentJobTarget],
    now: datetime | None = None,
) -> tuple[CommentScanCandidate, ...]:
    matched: list[CommentScanPost] = []
    for post in posts:
        key = (post.owner_id, post.source_key)
        preset = presets.get(key)
        policy = preset.comment_scan_policy if preset is not None else None
        if post.source_key == "hackernews" and policy is None:
            continue
        if (
            post.owner_id != topic.owner_id
            or post.source_key not in topic.source_keys
            or post.comment_count <= 0
            or preset is None
            or (
                now is not None
                and post.created_at
                < now - timedelta(seconds=policy.candidate_age_seconds if policy else 86_400)
            )
            or RecentCommentJobTarget(
                owner_id=post.owner_id,
                source_key=post.source_key,
                post_external_id=post.external_id,
            )
            in recent_jobs
            or not evaluate_monitor_rules(topic.rules, post.searchable_text).matched
        ):
            continue
        matched.append(post)
    ranked = sorted(matched, key=lambda item: (-item.interaction_score, str(item.content_id)))
    selected: list[CommentScanPost] = []
    counts: dict[str, int] = {}
    for post in ranked:
        policy = presets[(post.owner_id, post.source_key)].comment_scan_policy
        limit = policy.max_posts_per_topic if policy is not None else _COMMENT_TOPIC_LIMIT
        if counts.get(post.source_key, 0) >= limit:
            continue
        selected.append(post)
        counts[post.source_key] = counts.get(post.source_key, 0) + 1
    return tuple(
        CommentScanCandidate(
            post=post,
            topic=topic,
            preset=presets[(post.owner_id, post.source_key)],
        )
        for post in selected
    )


class CommentScanService:
    """Own candidate selection and comments Job acceptance for the scheduler."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue_due_comments_in_transaction(
        self, *, now: datetime, skip_bilibili: bool = False
    ) -> int:
        if not self._session.in_transaction():
            raise RuntimeError("comment scanning requires the caller's transaction")
        if now.tzinfo is None:
            raise ValueError("comment scan time must be timezone-aware")
        now_utc = now.astimezone(UTC)
        topics = MonitorScheduleService(
            self._session
        ).list_active_topics_for_scanning_in_transaction()
        presets = self._comment_presets(topics)
        if skip_bilibili:
            presets = {key: preset for key, preset in presets.items() if key[1] != "bilibili"}
        max_candidate_age = max(
            (
                preset.comment_scan_policy.candidate_age_seconds
                if preset.comment_scan_policy is not None
                else int(_COMMENT_POST_LIFETIME.total_seconds())
                for preset in presets.values()
            ),
            default=int(_COMMENT_POST_LIFETIME.total_seconds()),
        )
        posts = self._load_recent_posts(
            owners={topic.owner_id for topic in topics},
            source_keys={source_key for _, source_key in presets},
            since=now_utc - timedelta(seconds=max_candidate_age),
            until=now_utc,
        )
        recent_jobs: frozenset[RecentCommentJobTarget] = frozenset()
        for source_key in {source for _, source in presets}:
            source_presets = [preset for (_, key), preset in presets.items() if key == source_key]
            interval_seconds = max(
                (
                    preset.comment_scan_policy.refresh_interval_seconds
                    if preset.comment_scan_policy is not None
                    else int(_COMMENT_REFRESH_INTERVAL.total_seconds())
                    for preset in source_presets
                ),
                default=int(_COMMENT_REFRESH_INTERVAL.total_seconds()),
            )
            recent_jobs |= frozenset(
                target
                for target in load_recent_comment_job_targets_in_transaction(
                    self._session, since=now_utc - timedelta(seconds=interval_seconds)
                )
                if target.source_key == source_key
            )
        # Only a newer Bilibili search refreshes the cached comments. A standalone
        # comment scan must not replay the same JSONL as a fresh platform read.
        for post in posts:
            if post.source_key != "bilibili" or post.last_observed_at is None:
                continue
            target = RecentCommentJobTarget(
                owner_id=post.owner_id,
                source_key="bilibili",
                post_external_id=post.external_id,
            )
            if target in load_recent_comment_job_targets_in_transaction(
                self._session, since=post.last_observed_at
            ):
                recent_jobs |= frozenset({target})
        unique_candidates: dict[tuple[UUID, UUID], CommentScanCandidate] = {}
        for topic in topics:
            for candidate in _rank_comment_posts_for_topic(
                topic=topic,
                posts=posts,
                presets=presets,
                recent_jobs=recent_jobs,
                now=now_utc,
            ):
                unique_candidates.setdefault(
                    (candidate.post.owner_id, candidate.post.content_id), candidate
                )

        from content.comments import build_comment_job_acceptance

        accepted = 0
        logger = structlog.get_logger("comment_scan")
        for candidate in unique_candidates.values():
            try:
                policy = candidate.preset.comment_scan_policy
                interval_seconds = (
                    policy.refresh_interval_seconds
                    if policy is not None
                    else int(_COMMENT_REFRESH_INTERVAL.total_seconds())
                )
                bucket_start = comment_bucket_start(now_utc, interval_seconds=interval_seconds)
                with self._session.begin_nested():
                    JobService(self._session, clock=lambda: now_utc).accept_in_transaction(
                        owner_id=candidate.post.owner_id,
                        command=build_comment_job_acceptance(
                            _comment_collection_run(candidate, bucket_start=bucket_start)
                        ),
                    )
            except Exception as error:
                logger.warning(
                    "comment_scan_candidate_failed",
                    owner_id=str(candidate.post.owner_id),
                    topic_id=str(candidate.topic.topic_id),
                    content_id=str(candidate.post.content_id),
                    source_key=candidate.post.source_key,
                    error_type=type(error).__name__,
                    exc_info=True,
                )
                continue
            accepted += 1
        return accepted

    def _comment_presets(
        self,
        topics: tuple[ActiveTopicScan, ...],
    ) -> dict[tuple[UUID, str], AppliedSourcePreset]:
        sources_by_owner: dict[UUID, set[str]] = {}
        for topic in topics:
            sources_by_owner.setdefault(topic.owner_id, set()).update(topic.source_keys)
        result: dict[tuple[UUID, str], AppliedSourcePreset] = {}
        for owner_id in sorted(sources_by_owner, key=str):
            applied = load_applied_source_presets_in_transaction(
                self._session,
                owner_id=owner_id,
                source_keys=sorted(sources_by_owner[owner_id]),
            )
            for source_key, preset in applied.items():
                if SourceCapability.COMMENTS in preset.capabilities:
                    result[(owner_id, source_key)] = preset
        return result

    def _load_recent_posts(
        self,
        *,
        owners: set[UUID],
        source_keys: set[str],
        since: datetime,
        until: datetime,
    ) -> tuple[CommentScanPost, ...]:
        if not owners or not source_keys:
            return ()
        latest_versions = select(
            ContentVersion.owner_id.label("owner_id"),
            ContentVersion.content_id.label("content_id"),
            ContentVersion.title.label("title"),
            ContentVersion.body.label("body"),
            func.row_number()
            .over(
                partition_by=(ContentVersion.owner_id, ContentVersion.content_id),
                order_by=(ContentVersion.created_at.desc(), ContentVersion.id.desc()),
            )
            .label("position"),
        ).subquery()
        latest_observations = select(
            ContentObservation.owner_id.label("owner_id"),
            ContentObservation.content_id.label("content_id"),
            ContentObservation.like_count.label("like_count"),
            ContentObservation.comment_count.label("comment_count"),
            ContentObservation.repost_count.label("repost_count"),
            ContentObservation.observed_at.label("observed_at"),
            func.row_number()
            .over(
                partition_by=(ContentObservation.owner_id, ContentObservation.content_id),
                order_by=(
                    ContentObservation.observed_at.desc(),
                    ContentObservation.received_at.desc(),
                    ContentObservation.id.desc(),
                ),
            )
            .label("position"),
        ).subquery()
        rows = self._session.execute(
            select(
                ContentRecord.owner_id,
                ContentRecord.id,
                ContentRecord.source_key,
                ContentRecord.external_id,
                ContentRecord.created_at,
                latest_versions.c.title,
                latest_versions.c.body,
                latest_observations.c.like_count,
                latest_observations.c.comment_count,
                latest_observations.c.repost_count,
                latest_observations.c.observed_at,
            )
            .join(
                latest_versions,
                and_(
                    latest_versions.c.owner_id == ContentRecord.owner_id,
                    latest_versions.c.content_id == ContentRecord.id,
                    latest_versions.c.position == 1,
                ),
            )
            .join(
                latest_observations,
                and_(
                    latest_observations.c.owner_id == ContentRecord.owner_id,
                    latest_observations.c.content_id == ContentRecord.id,
                    latest_observations.c.position == 1,
                ),
            )
            .where(
                ContentRecord.owner_id.in_(owners),
                ContentRecord.source_key.in_(source_keys),
                ContentRecord.object_type == "post",
                or_(
                    ContentRecord.created_at >= since,
                    and_(
                        ContentRecord.source_key == "bilibili",
                        latest_observations.c.observed_at >= since,
                    ),
                ),
                ContentRecord.created_at <= until,
                latest_observations.c.comment_count > 0,
            )
            .order_by(ContentRecord.owner_id, ContentRecord.id)
        ).all()
        return tuple(
            CommentScanPost(
                owner_id=owner_id,
                content_id=content_id,
                source_key=source_key,
                external_id=external_id,
                created_at=(
                    created_at.replace(tzinfo=UTC)
                    if created_at.tzinfo is None
                    else created_at.astimezone(UTC)
                ),
                title=title,
                body=body,
                like_count=like_count,
                comment_count=comment_count,
                repost_count=repost_count,
                last_observed_at=(
                    observed_at.replace(tzinfo=UTC)
                    if observed_at.tzinfo is None
                    else observed_at.astimezone(UTC)
                ),
            )
            for (
                owner_id,
                content_id,
                source_key,
                external_id,
                created_at,
                title,
                body,
                like_count,
                comment_count,
                repost_count,
                observed_at,
            ) in rows
        )


def load_post_versions_for_analysis_scan(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    source_keys: tuple[str, ...],
    as_of: datetime | None = None,
    readable_at: datetime | None = None,
) -> tuple[AnalysisPostContentView, ...]:
    """Read selected search posts or versions from a matched hotlist observation."""
    if not session.in_transaction():
        raise RuntimeError("analysis content reads require the caller's transaction")
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("analysis scan cutoff must be timezone-aware")
    receipt_cutoff = (
        (ContentObservation.received_at < as_of.astimezone(UTC),) if as_of is not None else ()
    )
    readable = (
        (
            ContentObservation.id.in_(
                readable_resource_ids_query(
                    owner_id=owner_id,
                    resource_type=_RESOURCE_TYPE,
                    now=readable_at,
                )
            ),
        )
        if readable_at is not None
        else ()
    )
    occurred_at = case(
        (ContentRecord.source_key == "bilibili", ContentObservation.observed_at),
        else_=func.coalesce(ContentObservation.published_at, ContentObservation.observed_at),
    )
    recent_versions = (
        select(
            ContentObservation.content_version_id.label("content_version_id"),
            func.max(occurred_at).label("occurred_at"),
        )
        .join(
            ContentRecord,
            and_(
                ContentRecord.owner_id == ContentObservation.owner_id,
                ContentRecord.id == ContentObservation.content_id,
            ),
        )
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_version_id.is_not(None),
            *receipt_cutoff,
            *readable,
        )
        .group_by(ContentObservation.content_version_id)
        .subquery()
    )
    matched_hotlist_version = (
        select(HotlistEntryRecord.snapshot_id)
        .join(
            HotlistSnapshot,
            and_(
                HotlistSnapshot.id == HotlistEntryRecord.snapshot_id,
                HotlistSnapshot.owner_id == HotlistEntryRecord.owner_id,
            ),
        )
        .join(
            ContentObservation,
            and_(
                ContentObservation.owner_id == HotlistEntryRecord.owner_id,
                ContentObservation.content_id == HotlistEntryRecord.content_id,
                ContentObservation.job_id == HotlistSnapshot.job_id,
            ),
        )
        .where(
            HotlistEntryRecord.owner_id == owner_id,
            HotlistEntryRecord.content_id == ContentVersion.content_id,
            HotlistEntryRecord.matched_topic_ids.contains([str(topic_id)]),
            HotlistSnapshot.source_key == ContentRecord.source_key,
            ContentObservation.content_version_id == ContentVersion.id,
            *receipt_cutoff,
            *readable,
        )
        .correlate(ContentVersion, ContentRecord)
        .exists()
    )
    rows = session.execute(
        select(ContentVersion, ContentRecord)
        .join(recent_versions, recent_versions.c.content_version_id == ContentVersion.id)
        .join(
            ContentRecord,
            and_(
                ContentRecord.owner_id == ContentVersion.owner_id,
                ContentRecord.id == ContentVersion.content_id,
            ),
        )
        .where(
            ContentVersion.owner_id == owner_id,
            ContentRecord.object_type == "post",
            or_(ContentRecord.source_key.in_(source_keys), matched_hotlist_version),
        )
        .order_by(recent_versions.c.occurred_at, ContentVersion.id)
    ).all()
    return tuple(_analysis_post_view(version, content) for version, content in rows)


def load_post_analysis_availability_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    content_version_id: UUID,
) -> AnalysisPostAvailabilityView | None:
    """Read exact-version receipt and topic-matched hotlist facts."""
    if not session.in_transaction():
        raise RuntimeError("analysis content reads require the caller's transaction")
    row = session.execute(
        select(ContentVersion, ContentRecord)
        .join(
            ContentRecord,
            and_(
                ContentRecord.owner_id == ContentVersion.owner_id,
                ContentRecord.id == ContentVersion.content_id,
            ),
        )
        .where(
            ContentVersion.owner_id == owner_id,
            ContentVersion.id == content_version_id,
            ContentRecord.object_type == "post",
        )
    ).one_or_none()
    if row is None:
        return None
    version, content = row
    first_received_at = session.scalar(
        select(func.min(ContentObservation.received_at)).where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_id == content.id,
            ContentObservation.content_version_id == content_version_id,
        )
    )
    if first_received_at is None:
        return None
    first_hotlist_match_received_at = session.scalar(
        select(func.min(ContentObservation.received_at))
        .join(
            HotlistSnapshot,
            and_(
                HotlistSnapshot.owner_id == ContentObservation.owner_id,
                HotlistSnapshot.job_id == ContentObservation.job_id,
                HotlistSnapshot.source_key == content.source_key,
            ),
        )
        .join(
            HotlistEntryRecord,
            and_(
                HotlistEntryRecord.owner_id == ContentObservation.owner_id,
                HotlistEntryRecord.snapshot_id == HotlistSnapshot.id,
                HotlistEntryRecord.content_id == ContentObservation.content_id,
            ),
        )
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_id == content.id,
            ContentObservation.content_version_id == content_version_id,
            HotlistEntryRecord.matched_topic_ids.contains([str(topic_id)]),
        )
    )
    return AnalysisPostAvailabilityView(
        post=_analysis_post_view(version, content),
        source_key=content.source_key,
        first_received_at=first_received_at,
        first_hotlist_match_received_at=first_hotlist_match_received_at,
    )


def load_post_versions_for_analysis(
    session: Session,
    *,
    owner_id: UUID,
    content_version_ids: set[UUID],
    readable_at: datetime | None = None,
) -> tuple[AnalysisPostContentView, ...]:
    """Read exact immutable post versions frozen into an analysis job."""
    if not session.in_transaction():
        raise RuntimeError("analysis content reads require the caller's transaction")
    if not content_version_ids:
        return ()
    rows = session.execute(
        select(ContentVersion, ContentRecord)
        .join(
            ContentRecord,
            and_(
                ContentRecord.owner_id == ContentVersion.owner_id,
                ContentRecord.id == ContentVersion.content_id,
            ),
        )
        .where(
            ContentVersion.owner_id == owner_id,
            ContentVersion.id.in_(content_version_ids),
            ContentRecord.object_type == "post",
            *(_readable_version_conditions(owner_id=owner_id, now=readable_at)),
        )
        .order_by(ContentVersion.id)
    ).all()
    return tuple(_analysis_post_view(version, content) for version, content in rows)


def load_post_comments_for_analysis(
    session: Session,
    *,
    owner_id: UUID,
    post_content_ids: set[UUID],
    limit_per_post: int = 50,
    readable_at: datetime | None = None,
) -> dict[UUID, tuple[AnalysisCommentContentView, ...]]:
    """Return newest comment text; callers may request one extra truncation sentinel."""
    if not session.in_transaction():
        raise RuntimeError("analysis comment reads require the caller's transaction")
    if not 1 <= limit_per_post <= 51:
        raise ValueError("analysis comment limit must be between 1 and 51")
    if not post_content_ids:
        return {}

    version_rows = (
        select(
            ContentThread.post_content_id.label("post_content_id"),
            ContentVersion.content_id.label("comment_content_id"),
            ContentVersion.id.label("comment_version_id"),
            ContentVersion.title.label("title"),
            ContentVersion.body.label("body"),
            func.row_number()
            .over(
                partition_by=(ContentVersion.owner_id, ContentVersion.content_id),
                order_by=(ContentVersion.created_at.desc(), ContentVersion.id.desc()),
            )
            .label("version_position"),
        )
        .join(
            ContentVersion,
            and_(
                ContentVersion.owner_id == ContentThread.owner_id,
                ContentVersion.content_id == ContentThread.content_id,
            ),
        )
        .where(
            ContentThread.owner_id == owner_id,
            ContentThread.post_content_id.in_(post_content_ids),
            *_readable_version_conditions(owner_id=owner_id, now=readable_at),
        )
        .subquery()
    )
    latest_versions = (
        select(
            version_rows.c.post_content_id,
            version_rows.c.comment_content_id,
            version_rows.c.comment_version_id,
            version_rows.c.title,
            version_rows.c.body,
            func.row_number()
            .over(
                partition_by=version_rows.c.post_content_id,
                order_by=version_rows.c.comment_content_id,
            )
            .label("comment_position"),
        )
        .where(version_rows.c.version_position == 1)
        .subquery()
    )
    rows = session.execute(
        select(
            latest_versions.c.post_content_id,
            latest_versions.c.comment_content_id,
            latest_versions.c.comment_version_id,
            latest_versions.c.title,
            latest_versions.c.body,
        )
        .where(latest_versions.c.comment_position <= limit_per_post)
        .order_by(
            latest_versions.c.post_content_id,
            latest_versions.c.comment_position,
        )
    ).all()
    comments: dict[UUID, list[AnalysisCommentContentView]] = {}
    for post_content_id, comment_content_id, comment_version_id, title, body in rows:
        text = "\n".join(part for part in (title, body) if part)
        if not text:
            continue
        comments.setdefault(post_content_id, []).append(
            AnalysisCommentContentView(
                post_content_id=post_content_id,
                comment_content_id=comment_content_id,
                comment_version_id=comment_version_id,
                text=text,
            )
        )
    return {post_id: tuple(items) for post_id, items in comments.items()}


def _readable_version_conditions(
    *, owner_id: UUID, now: datetime | None
) -> tuple[ColumnElement[bool], ...]:
    if now is None:
        return ()
    return (
        select(ContentObservation.id)
        .where(
            ContentObservation.owner_id == owner_id,
            ContentObservation.content_id == ContentVersion.content_id,
            ContentObservation.content_version_id == ContentVersion.id,
            ContentObservation.id.in_(
                readable_resource_ids_query(
                    owner_id=owner_id,
                    resource_type=_RESOURCE_TYPE,
                    now=now,
                )
            ),
        )
        .correlate(ContentVersion)
        .exists(),
    )


def load_frozen_analysis_comments(
    session: Session,
    *,
    owner_id: UUID,
    version_ids: set[UUID],
    now: datetime,
) -> dict[UUID, AnalysisCommentContentView]:
    if not session.in_transaction():
        raise RuntimeError("analysis comment reads require the caller's transaction")
    if not version_ids:
        return {}
    rows = session.execute(
        select(ContentVersion, ContentThread.post_content_id)
        .join(
            ContentThread,
            and_(
                ContentThread.owner_id == ContentVersion.owner_id,
                ContentThread.content_id == ContentVersion.content_id,
            ),
        )
        .where(
            ContentVersion.owner_id == owner_id,
            ContentVersion.id.in_(version_ids),
            *_readable_version_conditions(owner_id=owner_id, now=now),
        )
    ).all()
    return {
        version.id: AnalysisCommentContentView(
            post_content_id=post_id,
            comment_content_id=version.content_id,
            comment_version_id=version.id,
            text="\n".join(part for part in (version.title, version.body) if part),
        )
        for version, post_id in rows
    }


def _analysis_post_view(
    version: ContentVersion,
    content: ContentRecord,
) -> AnalysisPostContentView:
    return AnalysisPostContentView(
        content_id=content.id,
        content_version_id=version.id,
        title=version.title,
        body=version.body,
    )


def load_event_content_inputs_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    version_ids: tuple[UUID, ...],
    since: datetime,
) -> dict[UUID, EventContentInputView]:
    """Return current content versions and their original source/time references."""
    if not session.in_transaction() or since.tzinfo is None:
        raise RuntimeError("event content reads require a transaction and aware time")
    if not version_ids:
        return {}
    rows = session.execute(
        select(ContentVersion, ContentRecord)
        .join(
            ContentRecord,
            (ContentRecord.owner_id == ContentVersion.owner_id)
            & (ContentRecord.id == ContentVersion.content_id),
        )
        .where(ContentVersion.owner_id == owner_id, ContentVersion.id.in_(version_ids))
    ).all()
    result: dict[UUID, EventContentInputView] = {}
    for version, record in rows:
        if record.source_key == "bilibili" or version.title is None or not version.title.strip():
            continue
        latest_id = session.scalar(
            select(ContentVersion.id)
            .where(ContentVersion.owner_id == owner_id, ContentVersion.content_id == record.id)
            .order_by(ContentVersion.created_at.desc(), ContentVersion.id.desc())
            .limit(1)
        )
        if latest_id != version.id:
            continue
        published_at, observed_at = session.execute(
            select(
                func.min(ContentObservation.published_at),
                func.min(ContentObservation.observed_at),
            ).where(
                ContentObservation.owner_id == owner_id,
                ContentObservation.content_id == record.id,
            )
        ).one()
        first_seen_at = published_at or observed_at or record.created_at
        if first_seen_at < since:
            continue
        representative_comment_id = (
            record.id
            if record.object_type == "comment"
            else session.scalar(
                select(ContentThread.content_id)
                .where(
                    ContentThread.owner_id == owner_id,
                    ContentThread.post_content_id == record.id,
                )
                .order_by(ContentThread.created_at, ContentThread.content_id)
                .limit(1)
            )
        )
        result[version.id] = EventContentInputView(
            content_id=record.id,
            content_version_id=version.id,
            source_key=record.source_key,
            title=version.title,
            body=version.body,
            first_seen_at=first_seen_at,
            first_seen_basis="published" if published_at is not None else "discovered",
            representative_comment_id=representative_comment_id,
        )
    return result
