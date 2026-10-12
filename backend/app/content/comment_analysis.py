"""Read already collected comment threads; never fetch missing parent material."""

from datetime import datetime
from itertools import pairwise
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from content.comment_analysis_schemas import CommentAnalysisContext, CommentContextText
from content.models import ContentObservation, ContentRecord, ContentThread, ContentVersion
from content.schemas import AnalysisPostContentView
from content.services import load_post_versions_for_analysis_scan
from evidence.services import readable_resource_ids_query


def _text(
    session: Session,
    *,
    owner_id: UUID,
    content_id: UUID,
    now: datetime,
    version_id: UUID | None = None,
    observation_id: UUID | None = None,
) -> CommentContextText | None:
    query = (
        select(ContentVersion, ContentObservation.id)
        .join(
            ContentObservation,
            (ContentObservation.owner_id == ContentVersion.owner_id)
            & (ContentObservation.content_version_id == ContentVersion.id),
        )
        .where(
            ContentVersion.owner_id == owner_id,
            ContentVersion.content_id == content_id,
            ContentVersion.created_at <= now,
            ContentObservation.received_at <= now,
            ContentObservation.id.in_(
                readable_resource_ids_query(
                    owner_id=owner_id,
                    resource_type="content_observation",
                    now=now,
                )
            ),
        )
    )
    if version_id is not None:
        query = query.where(
            ContentVersion.id == version_id, ContentObservation.id == observation_id
        )
    row = session.execute(
        query.order_by(
            ContentVersion.created_at.desc(),
            ContentVersion.id.desc(),
            ContentObservation.received_at.desc(),
            ContentObservation.id.desc(),
        ).limit(1)
    ).first()
    if row is None:
        return None
    version, observation = row
    body = "\n".join(part for part in (version.title, version.body) if part)
    if not body.strip():
        return None
    return CommentContextText(
        content_id=content_id,
        content_version_id=version.id,
        observation_id=observation,
        text=body[:1500],
        truncated=len(body) > 1500,
    )


def load_comment_analysis_page_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    post: AnalysisPostContentView,
    now: datetime,
    after: UUID | None = None,
) -> tuple[tuple[CommentAnalysisContext, ...], UUID | None]:
    """Freeze at most 50 collected comments and eight available direct ancestors.

    Returns:
        Frozen readable contexts and a raw thread cursor, including unreadable rows.

    Raises:
        RuntimeError: The caller has no transaction or provides a naive clock.
    """
    if not session.in_transaction() or now.utcoffset() is None:
        raise RuntimeError("comment context reads require an aware caller transaction")
    original = _text(
        session,
        owner_id=owner_id,
        content_id=post.content_id,
        now=now,
        version_id=post.content_version_id,
        observation_id=post.observation_id,
    )
    if original is None:
        return (), None
    query = select(ContentThread).where(
        ContentThread.owner_id == owner_id,
        ContentThread.post_content_id == post.content_id,
    )
    if after is not None:
        query = query.where(ContentThread.content_id > after)
    threads = tuple(session.scalars(query.order_by(ContentThread.content_id).limit(50)))
    result: list[CommentAnalysisContext] = []
    for thread in threads:
        target = _text(session, owner_id=owner_id, content_id=thread.content_id, now=now)
        if target is None:
            continue
        parents: list[CommentContextText] = []
        seen = {thread.content_id}
        current = thread
        state = "root" if current.parent_relation_status == "root" else "complete"
        while current.parent_content_id is not None:
            parent_id = current.parent_content_id
            if parent_id in seen:
                state = "cycle"
                break
            if len(parents) == 8:
                state = "depth_limit"
                break
            parent_thread = session.get(ContentThread, (owner_id, parent_id))
            if parent_thread is None or parent_thread.post_content_id != post.content_id:
                state = (
                    "unresolved" if current.parent_relation_status == "unresolved" else "missing"
                )
                break
            parent = _text(session, owner_id=owner_id, content_id=parent_id, now=now)
            if parent is None:
                state = (
                    "unresolved"
                    if current.parent_relation_status == "unresolved"
                    else "unavailable"
                )
                break
            parents.append(parent)
            seen.add(parent_id)
            current = parent_thread
        if current.parent_content_id is None and current.parent_relation_status != "root":
            state = "unresolved"
        result.append(
            CommentAnalysisContext.model_validate(
                {
                    "post": original,
                    "target": target,
                    "parents": tuple(parents),
                    "parent_state": state,
                    "next_parent_id": current.parent_content_id
                    if state not in {"root", "complete"}
                    else None,
                }
            )
        )
    return tuple(result), threads[-1].content_id if len(threads) == 50 else None


def require_frozen_comment_context_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    context: CommentAnalysisContext,
    now: datetime,
) -> None:
    """Recheck exact text/observations and owner/post membership without reading latest.

    Missing ancestors stay missing even if a later collection fills the gap.

    Raises:
        ValueError: Frozen text, version, observation or thread membership is unavailable.
    """
    for item in (context.post, context.target, *context.parents):
        actual = _text(
            session,
            owner_id=owner_id,
            content_id=item.content_id,
            now=now,
            version_id=item.content_version_id,
            observation_id=item.observation_id,
        )
        if actual is None or (
            actual != item
            and not (
                item.truncated
                and actual.text.startswith(item.text)
                and actual.content_version_id == item.content_version_id
                and actual.observation_id == item.observation_id
                and actual.content_id == item.content_id
            )
        ):
            raise ValueError("frozen comment context is unavailable")
    for item in (context.target, *context.parents):
        thread = session.get(ContentThread, (owner_id, item.content_id))
        if thread is None or thread.post_content_id != context.post.content_id:
            raise ValueError("comment context belongs to a different post")
    chain = (context.target, *context.parents)
    for current, parent in pairwise(chain):
        thread = session.get(ContentThread, (owner_id, current.content_id))
        if thread is None or thread.parent_content_id != parent.content_id:
            raise ValueError("comment context parent relation changed")


def load_comment_analysis_post_page_in_transaction(
    session: Session,
    *,
    owner_id: UUID,
    topic_id: UUID,
    topic_rule_version: int,
    source_keys: tuple[str, ...],
    now: datetime,
    after: UUID | None,
    resume: bool,
) -> tuple[tuple[AnalysisPostContentView, ...], UUID | None, bool]:
    """Return current readable posts within fifty raw versions and a fair cursor.

    Historical versions advance the raw cursor but never create competing contexts
    for the same comment in one scan. Existing jobs still retain their exact version.

    Returns:
        Eligible frozen posts, the last raw version and whether this cycle is exhausted.

    Raises:
        RuntimeError: No caller transaction is active.
    """
    if not session.in_transaction():
        raise RuntimeError("comment post pagination requires caller transaction")
    query = (
        select(ContentVersion.id)
        .join(
            ContentRecord,
            (ContentRecord.owner_id == ContentVersion.owner_id)
            & (ContentRecord.id == ContentVersion.content_id),
        )
        .where(ContentVersion.owner_id == owner_id, ContentRecord.object_type == "post")
    )
    if after is not None:
        query = query.where(ContentVersion.id >= after if resume else ContentVersion.id > after)
    versions = tuple(session.scalars(query.order_by(ContentVersion.id).limit(50)))
    if not versions:
        return (), None, True
    posts = load_post_versions_for_analysis_scan(
        session,
        owner_id=owner_id,
        topic_id=topic_id,
        topic_rule_version=topic_rule_version,
        source_keys=source_keys,
        readable_at=now,
        candidate_version_ids=set(versions),
    )
    current_posts = []
    for post in posts:
        current = _text(session, owner_id=owner_id, content_id=post.content_id, now=now)
        if current is not None and current.content_version_id == post.content_version_id:
            current_posts.append(post)
    return (
        tuple(sorted(current_posts, key=lambda item: item.content_version_id)),
        versions[-1],
        len(versions) < 50,
    )
