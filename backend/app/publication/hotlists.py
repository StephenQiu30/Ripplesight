"""Public whole-board projection: independent grant, current raw proof, then freshness."""

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from connections.services import list_applied_hotlist_presets_in_transaction
from content.hotlist_reading import (
    BoardUnavailableError,
    compare_boards_in_transaction,
    latest_board_id_in_transaction,
    read_board_in_transaction,
)
from evidence.admission_reading import load_current_source_admissions_in_transaction
from evidence.schemas import DataClass
from evidence.services import load_source_access_policy_in_transaction
from jobs.coverage import latest_hotlist_run_in_transaction
from publication.hotlist_schemas import (
    HotlistPublicationGrant,
    PublicPlatformEntry,
    PublicPlatformTrend,
)
from publication.publication_models import PublicationSourcePolicy
from sources.adapters.web_targets import normalize_public_article_url
from sources.contracts import SourceCapability

SOURCES = {
    "hotlist_weibo": "微博热搜",
    "hotlist_baidu": "百度热榜",
    "hotlist_zhihu": "知乎热榜",
    "hotlist_bilibili": "B站热门",
    "hotlist_36kr": "36Kr热榜",
    "hotlist_thepaper": "澎湃精选",
}


def public_platform_trends_in_transaction(
    session: Session, *, owner_id: UUID, now: datetime
) -> list[PublicPlatformTrend]:
    """Read six fixed source identities without leaking private snapshot existence.

    No source HTTP, task acceptance or writes occur. The caller owns the same
    repeatable-read read-only transaction as the home overview.
    """
    if not session.in_transaction() or now.utcoffset() is None:
        raise ValueError("public platform trends require aware caller snapshot")
    result = []
    # Connections and raw admissions are queried only after a public grant succeeds.
    applied = None
    for key, name in SOURCES.items():
        output = PublicPlatformTrend(
            source_key=key, source_name=name, state="not_configured", reasons=["permission_missing"]
        )
        result.append(output)
        policy = session.get(PublicationSourcePolicy, (owner_id, key))
        raw = policy.configuration.get("hotlist_publication") if policy else None
        try:
            grant = HotlistPublicationGrant.model_validate(raw) if raw is not None else None
        except ValidationError:
            continue
        if (
            grant is None
            or not grant.enabled
            or policy is None
            or policy.configuration.get("participation_mode") != "hot_signal"
        ):
            continue
        if not grant.reviewed_at <= now < grant.expires_at:
            output.reasons = ["permission_expired"]
            continue
        source_policy = load_source_access_policy_in_transaction(
            session,
            owner_id=owner_id,
            source_key=key,
            capability=SourceCapability.HOTLIST,
            lock=False,
        )
        if (
            source_policy is not None
            and source_policy.policy_version != grant.source_policy_version
        ):
            output.reasons = ["policy_changed"]
            continue
        admission = load_current_source_admissions_in_transaction(
            session,
            owner_id=owner_id,
            source_contexts={(key, SourceCapability.HOTLIST)},
            data_class=DataClass.STRUCTURED,
            now=now,
        ).get((key, SourceCapability.HOTLIST))
        if admission is not None and admission.policy_version != grant.source_policy_version:
            output.reasons = ["policy_changed"]
            continue
        if admission is not None and not set(grant.board_fields + grant.entry_fields).issubset(
            admission.field_purposes
        ):
            output.reasons = ["policy_changed"]
            continue
        output.state = "unavailable"
        output.reasons = ["source_unavailable"]
        if applied is None:
            applied = {
                item.source_key: item
                for item in list_applied_hotlist_presets_in_transaction(
                    session, owner_id=owner_id, lock=False
                )
            }
        current_connection = applied.get(key)
        if (
            admission is None
            or current_connection is None
            or not set(grant.board_fields + grant.entry_fields).issubset(admission.field_purposes)
        ):
            continue
        identifier = latest_board_id_in_transaction(session, owner_id=owner_id, source_key=key)
        board = None
        if identifier is not None:
            try:
                board = read_board_in_transaction(
                    session, owner_id=owner_id, snapshot_id=identifier, now=now
                )
            except BoardUnavailableError as error:
                output.reasons = [error.reason]
                continue
            if (board.connection_id, board.connection_version) != (
                current_connection.connection_id,
                current_connection.connection_version,
            ):
                output.reasons = ["source_changed"]
                continue
        run = latest_hotlist_run_in_transaction(session, owner_id=owner_id, source_key=key, now=now)
        if run is not None and (board is None or run.due_at > board.due_at):
            output.due_at = run.due_at
            output.last_success_at = board.observed_at if board else None
            if run.skipped:
                output.state = "unavailable"
                output.reasons = ["collection_skipped"]
            elif run.status in {"queued", "running", "retry_scheduled"}:
                output.state = "collecting"
                output.reasons = ["collection_pending"]
            else:
                output.state = "failed"
                output.reasons = ["collection_failed"]
            continue
        if board is None:
            output.state = "no_snapshot"
            output.reasons = ["snapshot_missing"]
            continue
        output.snapshot_id = board.snapshot_id
        output.observed_at = board.observed_at
        output.received_at = board.received_at
        output.source_updated_at = (
            board.source_updated_at if "source_updated_at" in grant.board_fields else None
        )
        output.due_at = board.due_at
        output.last_success_at = board.observed_at
        output.valid_until = min(
            board.expires_at,
            grant.expires_at,
            board.observed_at + timedelta(seconds=grant.max_age_seconds),
        )
        output.adapter_version = board.adapter_version
        output.license_name = grant.license_name
        output.license_url = grant.license_url
        output.permission_reviewed_at = grant.reviewed_at
        output.permission_expires_at = grant.expires_at
        if now > output.valid_until:
            output.state = "stale"
            output.reasons = ["snapshot_stale"]
            continue
        reason, previous = compare_boards_in_transaction(
            session, owner_id=owner_id, board=board, now=now
        )
        # Both the reason and ranks are derived on the server; absent means unknown, never new.
        if reason == "comparable":
            output.comparison_reason = "comparable"
        elif reason == "gap":
            output.comparison_reason = "gap"
        elif reason == "source_changed":
            output.comparison_reason = "source_changed"
        elif reason == "unavailable":
            output.comparison_reason = "unavailable"
        allowed = set(grant.entry_fields)
        for item in board.items:
            values = item.model_dump(exclude={"fields", "rank", "title", "url"})
            values = {field: value for field, value in values.items() if field in allowed}
            old = previous.get(normalize_public_article_url(item.url))
            output.items.append(
                PublicPlatformEntry(
                    rank=item.rank,
                    title=item.title,
                    url=item.url,
                    **values,
                    previous_rank=old,
                    rank_delta=old - item.rank if old is not None else None,
                )
            )
        output.entry_count = len(output.items)
        output.source_entry_count = board.source_entry_count
        output.truncated = board.truncated
        reasons = []
        if board.truncated:
            reasons.append("truncated")
        if output.source_updated_at is None:
            reasons.append("source_time_unknown")
        if any(item.native_rank is None for item in output.items):
            reasons.append("native_rank_unknown")
        if any(item.native_id is None for item in output.items):
            reasons.append("native_id_unknown")
        if any(item.heat is None or item.heat_unit is None for item in output.items):
            reasons.append("native_metric_unknown")
        output.state = "empty" if not output.items else "partial" if reasons else "available"
        output.reasons = reasons
    return result
