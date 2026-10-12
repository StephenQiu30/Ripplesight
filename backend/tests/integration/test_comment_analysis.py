"""Frozen per-comment jobs use real isolated storage and an entirely controlled model."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_analysis_pipeline import (
    _make_unreadable,
    _seed_comment_version,
)
from tests.integration.test_analysis_pipeline import analysis_case as analysis_case

from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from analysis.comments import CommentAnalysisService
from analysis.models import ContentAnnotation
from analysis.prompts import COMMENT_ANALYSIS_PROMPT_VERSION
from analysis.reads import load_content_annotations_in_transaction
from analysis.schemas import AnalysisJobScope
from analysis.services import (
    AnalysisAnnotateExecutor,
    list_relevant_event_annotation_refs_in_transaction,
)
from content.comment_analysis import load_comment_analysis_page_in_transaction
from content.services import ContentService, load_post_versions_for_analysis
from core.config import Settings
from jobs.execution import JobExecutionFailure
from jobs.schemas import JobAcceptedMessage
from jobs.services import load_job_execution_configuration


class ControlledCommentClient:
    provider = "controlled"
    model = "controlled-comment"

    def __init__(self):
        self.calls = []
        self.output = {}
        self.failure = None
        self.callback = None

    def complete(self, *, prompt, output_schema, instructions=""):
        self.calls.append(prompt)
        if self.callback is not None:
            self.callback()
        if self.failure is not None:
            raise AiCallError(self.failure)
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output=self.output,
            usage=AiTokenUsage(),
            duration_ms=1,
        )

    def close(self):
        pass


def _scan(case):
    with case.sessions() as session, session.begin():
        return CommentAnalysisService(
            session,
            settings=Settings(
                _env_file=None, database_url=case.sessions.kw["bind"].url.render_as_string(False)
            ),
        ).enqueue_due_in_transaction(
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            now=case.now,
        )


def _message(case, job):
    with case.sessions() as session:
        row = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job.id},
        ).one()
    return JobAcceptedMessage.model_validate(
        {**row.payload, "message_id": row.id, "event_type": row.event_type, "schema_version": 2}
    )


def _executor(case, monkeypatch, client):
    _enable_ai_budget(case.sessions.kw["bind"], case.owner_id)
    with case.sessions.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET window_anchor_at=:now "
                "WHERE owner_id=:owner AND budget_key='global.analysis-attempts'"
            ),
            {"now": case.now, "owner": case.owner_id},
        )
    monkeypatch.setattr("analysis.services.create_ai_client", lambda settings: client)

    def frozen(settings, model):
        client.frozen_model = model
        client.provider, client.model = model.provider, model.model
        return client

    monkeypatch.setattr("ai.services.create_ai_client_for_frozen_model", frozen)
    return AnalysisAnnotateExecutor(
        case.sessions,
        Settings(
            _env_file=None,
            database_url=case.sessions.kw["bind"].url.render_as_string(False),
            ai_enabled=True,
        ),
        clock=lambda: case.now,
    )


def _reply(case, parent, body="是这样", *, status="observed", post=None):
    identifier = uuid4()
    with case.sessions() as session, session.begin():
        session.execute(
            text(
                "INSERT INTO content_records "
                "(id,owner_id,source_key,object_type,external_id,created_at) "
                "VALUES (:id,:owner,'hackernews','comment',:external,:now)"
            ),
            {"id": identifier, "owner": case.owner_id, "external": identifier.hex, "now": case.now},
        )
        session.execute(
            text(
                "INSERT INTO content_threads "
                "(owner_id,content_id,post_content_id,parent_content_id,"
                "parent_relation_status,created_at) "
                "VALUES (:owner,:id,:post,:parent,:status,:now)"
            ),
            {
                "owner": case.owner_id,
                "id": identifier,
                "post": post or case.content_id,
                "parent": parent,
                "status": status,
                "now": case.now,
            },
        )
        _seed_comment_version(session, case.owner_id, identifier, body, case.now)
        session.execute(
            text(
                "INSERT INTO content_discoveries "
                "(id,owner_id,content_id,job_id,first_observed_at,created_at) "
                "SELECT :id,owner_id,content_id,job_id,observed_at,received_at "
                "FROM content_observations WHERE content_id=:content LIMIT 1"
            ),
            {"id": uuid4(), "content": identifier},
        )
    return identifier


def _scopes(case):
    jobs = _scan(case)
    with case.sessions() as session, session.begin():
        scopes = [
            (
                job,
                AnalysisJobScope.from_job_scope(
                    load_job_execution_configuration(session, job_id=job.id).scope
                ),
            )
            for job in jobs
        ]
    return {scope.prompt_items[0].content_id: (job, scope) for job, scope in scopes}


@pytest.mark.parametrize(
    "state,relevant", [("valid", True), ("valid", False), ("insufficient", None), ("unknown", None)]
)
def test_contextual_comment_outcomes_persist_read_and_replay_without_extra_calls(
    analysis_case, monkeypatch, state, relevant
):
    case = analysis_case
    reply = _reply(case, case.comment_id)
    job, scope = _scopes(case)[reply]
    context = scope.prompt_items[0].comment_context
    assert context.post.content_version_id == case.version_id
    assert context.target.text == "是这样" and "HotKey" not in context.target.text
    assert context.parents[0].text == "原评论" and context.parent_state == "complete"
    client = ControlledCommentClient()
    client.output = {
        "items": [
            {
                "content_version_id": str(context.target.content_version_id),
                "state": state,
                "relevant": relevant,
                "relevance_reason": "结合原帖与父评论判断",
                "summary": "评论独立结论" if state == "valid" else None,
            }
        ]
    }
    executor = _executor(case, monkeypatch, client)
    result = executor.execute(_message(case, job))
    assert result.completion.status.value == "succeeded"
    assert len(client.calls) == 1 and "原评论" in client.calls[0]
    executor.execute(_message(case, job))
    assert len(client.calls) == 1
    with case.sessions() as session, session.begin():
        annotations = load_content_annotations_in_transaction(
            session,
            owner_id=case.owner_id,
            content_id=reply,
            readable_version_ids={context.target.content_version_id},
            now=case.now,
        )
        assert len(annotations) == 1 and annotations[0].result_state.value == state
        assert annotations[0].relevant is relevant and annotations[0].sentiment is None
        assert not list_relevant_event_annotation_refs_in_transaction(
            session, since=case.now - timedelta(days=10), now=case.now
        ).items
    with case.sessions() as session:
        detail = ContentService(session, clock=lambda: case.now).get_content(
            owner_id=case.owner_id, content_id=reply
        )
    assert detail.analysis_prompt_version == COMMENT_ANALYSIS_PROMPT_VERSION
    assert detail.annotations[0].result_state.value == state
    assert _scan(case) == ()


def test_rate_limit_preserves_deferred_state_and_exact_original_context(analysis_case, monkeypatch):
    case = analysis_case
    reply = _reply(case, case.comment_id)
    job, scope = _scopes(case)[reply]
    client = ControlledCommentClient()
    client.failure = AiFailureCode.RATE_LIMITED
    executor = _executor(case, monkeypatch, client)
    with pytest.raises(JobExecutionFailure) as caught:
        executor.execute(_message(case, job))
    assert caught.value.error_code == "analysis_rate_limited" and caught.value.retry_at > case.now
    with case.sessions() as session, session.begin():
        row = session.scalars(
            select(ContentAnnotation).where(ContentAnnotation.content_id == reply)
        ).one()
        assert (
            row.result_state == "deferred" and row.relevant is None and row.ai_call_id is not None
        )
        assert row.error_code == "analysis_rate_limited"
        _seed_comment_version(
            session, case.owner_id, case.comment_id, "后来父评论", case.now + timedelta(seconds=1)
        )
    client.failure = None
    client.output = {
        "items": [
            {
                "content_version_id": str(scope.content_version_ids[0]),
                "state": "valid",
                "relevant": True,
                "relevance_reason": "旧上下文仍可判断",
                "summary": "短回复结论",
            }
        ]
    }
    executor.execute(_message(case, job))
    assert client.calls[1] == client.calls[0] and "后来父评论" not in client.calls[1]
    # New material gets its own signature; the delayed task never adopts it.
    changed = _scopes(replace(case, now=case.now + timedelta(seconds=2)))[reply][1]
    assert changed.input_manifest.signature != scope.input_manifest.signature
    assert changed.prompt_items[0].comment_context.parents[0].text == "后来父评论"


@pytest.mark.parametrize("target", ["post", "parent", "comment"])
def test_each_frozen_context_permission_is_rechecked_before_model_call(
    analysis_case, monkeypatch, target
):
    case = analysis_case
    reply = _reply(case, case.comment_id)
    job, scope = _scopes(case)[reply]
    client = ControlledCommentClient()
    executor = _executor(case, monkeypatch, client)
    _make_unreadable(
        case,
        {"post": case.content_id, "parent": case.comment_id, "comment": reply}[target],
        "expired",
    )
    with pytest.raises(JobExecutionFailure):
        executor.execute(_message(case, job))
    assert not client.calls
    with case.sessions() as session, session.begin():
        assert not load_content_annotations_in_transaction(
            session,
            owner_id=case.owner_id,
            content_id=reply,
            readable_version_ids=set(scope.content_version_ids),
            now=case.now,
        )


def test_available_parent_chain_is_bounded_and_missing_parent_is_not_invented(analysis_case):
    case = analysis_case
    current = case.comment_id
    for _ in range(10):
        current = _reply(case, current)
    with case.sessions() as session, session.begin():
        post = load_post_versions_for_analysis(
            session,
            owner_id=case.owner_id,
            content_version_ids={case.version_id},
            readable_at=case.now,
        )[0]
        contexts, _ = load_comment_analysis_page_in_transaction(
            session, owner_id=case.owner_id, post=post, now=case.now
        )
        context = next(item for item in contexts if item.target.content_id == current)
        assert len(context.parents) == 8 and context.parent_state == "depth_limit"
    _make_unreadable(case, case.comment_id, "expired")
    with case.sessions() as session, session.begin():
        contexts, _ = load_comment_analysis_page_in_transaction(
            session, owner_id=case.owner_id, post=post, now=case.now
        )
        assert any(item.parent_state == "unavailable" for item in contexts)


def test_comment_scan_pages_beyond_first_fifty_without_duplicate_jobs(analysis_case):
    case = analysis_case
    for index in range(52):
        _reply(case, case.comment_id, f"短回复{index}")
    accepted = []
    for _ in range(4):
        jobs = _scan(case)
        assert len(jobs) <= 20
        accepted.extend(jobs)
    assert len(accepted) == 53 and len({job.id for job in accepted}) == 53
    assert _scan(case) == ()


def test_new_comment_jobs_use_only_latest_readable_post_version(analysis_case):
    case = analysis_case
    _reply(case, case.comment_id)
    with case.sessions.begin() as session:
        _seed_comment_version(
            session, case.owner_id, case.content_id, "HotKey 更新后的原帖", case.now
        )
    jobs = _scan(case)
    assert len(jobs) == 2
    with case.sessions() as session:
        for job in jobs:
            scope = AnalysisJobScope.from_job_scope(
                load_job_execution_configuration(session, job_id=job.id).scope
            )
            context = scope.prompt_items[0].comment_context
            assert context.post.text == "HotKey 更新后的原帖"
            assert context.post.content_version_id != case.version_id
    assert _scan(case) == ()


def test_timeout_outcome_remains_unknown_and_replay_never_sends_again(analysis_case, monkeypatch):
    case = analysis_case
    reply = _reply(case, case.comment_id)
    job, _scope = _scopes(case)[reply]
    client = ControlledCommentClient()
    client.failure = AiFailureCode.TIMEOUT
    executor = _executor(case, monkeypatch, client)
    with pytest.raises(JobExecutionFailure):
        executor.execute(_message(case, job))
    with case.sessions() as session:
        row = session.scalars(
            select(ContentAnnotation).where(ContentAnnotation.content_id == reply)
        ).one()
        assert row.result_state == "unknown" and row.relevant is None
        assert row.error_code == "analysis_timeout" and row.relevance_reason
        assert (
            session.execute(
                text("SELECT status FROM ai_calls WHERE id=:call"), {"call": row.ai_call_id}
            ).scalar_one()
            == "unknown"
        )
    with pytest.raises(JobExecutionFailure) as caught:
        executor.execute(_message(case, job))
    assert caught.value.error_code == "analysis_outcome_unknown" and len(client.calls) == 1
    assert _scan(case) == ()


def test_rate_limit_before_call_keeps_deferred_without_inventing_call_identity(
    analysis_case, monkeypatch
):
    case = analysis_case
    job, scope = _scopes(case)[case.comment_id]

    def unavailable(settings):
        raise AiCallError(AiFailureCode.RATE_LIMITED)

    monkeypatch.setattr("analysis.services.create_ai_client", unavailable)
    executor = AnalysisAnnotateExecutor(
        case.sessions,
        Settings(_env_file=None, database_url=case.sessions.kw["bind"].url.render_as_string(False)),
        clock=lambda: case.now,
    )
    with pytest.raises(JobExecutionFailure):
        executor.execute(_message(case, job))
    with case.sessions() as session:
        row = session.scalars(select(ContentAnnotation)).one()
        assert row.result_state == "deferred" and row.ai_call_id is None
        assert row.relevant is None and row.input_signature == scope.input_manifest.signature
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 0


def test_invalid_compensation_preserves_model_and_original_parent_context_once(
    analysis_case, monkeypatch
):
    case = analysis_case
    reply = _reply(case, case.comment_id)
    job, scope = _scopes(case)[reply]
    client = ControlledCommentClient()
    client.output = {"items": []}
    executor = _executor(case, monkeypatch, client)
    result = executor.execute(_message(case, job))
    assert result.completion.status.value == "partially_succeeded"
    with case.sessions() as session, session.begin():
        session.execute(
            text("UPDATE jobs SET status='partially_succeeded' WHERE id=:id"), {"id": job.id}
        )
        _seed_comment_version(
            session, case.owner_id, case.comment_id, "后来才出现的父评论", case.now
        )
    jobs = _scan(case)
    with case.sessions() as session:
        scopes = [
            (
                j,
                AnalysisJobScope.from_job_scope(
                    load_job_execution_configuration(session, job_id=j.id).scope
                ),
            )
            for j in jobs
        ]
    retry_job, retry = next((j, s) for j, s in scopes if s.retry_index == 1)
    assert retry.prompt_items == scope.prompt_items and retry.input_manifest == scope.input_manifest
    with case.sessions() as session:
        assert (
            load_job_execution_configuration(session, job_id=retry_job.id).scope["ai_routing"]
            == load_job_execution_configuration(session, job_id=job.id).scope["ai_routing"]
        )
    executor.execute(_message(case, retry_job))
    assert client.calls[0] == client.calls[1] and "后来才出现" not in client.calls[1]
    with case.sessions() as session:
        row = session.scalars(
            select(ContentAnnotation).where(
                ContentAnnotation.content_id == reply,
                ContentAnnotation.input_signature == scope.input_manifest.signature,
            )
        ).one()
        assert row.result_state == "failed" and row.error_code == "analysis_invalid_exhausted"
    assert _scan(case) == ()
    with case.sessions() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM jobs WHERE scope->>'retry_index'='1'")
            ).scalar_one()
            == 1
        )


def test_invalid_compensation_rotates_past_twenty_cancelled_candidates(analysis_case, monkeypatch):
    case = analysis_case
    reply = _reply(case, case.comment_id)
    scopes = _scopes(case)
    client = ControlledCommentClient()
    client.output = {"items": []}
    executor = _executor(case, monkeypatch, client)
    for job, _ in scopes.values():
        executor.execute(_message(case, job))
    cancelled, _ = scopes[case.comment_id]
    eligible, _ = scopes[reply]
    with case.sessions.begin() as session:
        session.execute(
            text("UPDATE jobs SET status='partially_succeeded' WHERE id=:id"),
            {"id": eligible.id},
        )
        session.execute(
            text("UPDATE jobs SET status='cancelled',cancel_requested_at=:now WHERE id=:id"),
            {"id": cancelled.id, "now": case.now},
        )
        rows = {r.content_id: r for r in session.scalars(select(ContentAnnotation))}
        blocked = rows[case.comment_id]
        blocked.id = UUID(int=1)
        rows[reply].id = UUID(int=21)
        values = {c.name: getattr(blocked, c.name) for c in ContentAnnotation.__table__.columns}
        for index in range(2, 21):
            session.add(
                ContentAnnotation(
                    **{**values, "id": UUID(int=index), "input_signature": f"{index:064x}"}
                )
            )
    assert _scan(case) == ()
    retries = _scan(case)
    assert len(retries) == 1
    with case.sessions() as session:
        retry = AnalysisJobScope.from_job_scope(
            load_job_execution_configuration(session, job_id=retries[0].id).scope
        )
    assert retry.retry_index == 1 and retry.prompt_items[0].content_id == reply
    assert len(client.calls) == 2  # Scanning itself never asks a model.


def test_revoke_parent_during_call_hides_output_and_blocks_persistence(analysis_case, monkeypatch):
    case = analysis_case
    reply = _reply(case, case.comment_id)
    job, scope = _scopes(case)[reply]
    client = ControlledCommentClient()
    client.output = {
        "items": [
            {
                "content_version_id": str(scope.content_version_ids[0]),
                "state": "valid",
                "relevant": True,
                "relevance_reason": "受控结论",
                "summary": "摘要",
            }
        ]
    }
    client.callback = lambda: _make_unreadable(case, case.comment_id, "expired")
    executor = _executor(case, monkeypatch, client)
    with pytest.raises(JobExecutionFailure):
        executor.execute(_message(case, job))
    assert len(client.calls) == 1
    with case.sessions() as session:
        row = session.scalars(
            select(ContentAnnotation).where(ContentAnnotation.content_id == reply)
        ).one()
        assert row.result_state == "pending" and row.relevant is None


@pytest.mark.parametrize(
    "mode,expected", [("missing", "missing"), ("unresolved", "unresolved"), ("cycle", "cycle")]
)
def test_missing_unresolved_and_cyclic_parent_relations_remain_explicit(
    analysis_case, mode, expected
):
    case = analysis_case
    reply = _reply(
        case, case.comment_id, status="unresolved" if mode == "unresolved" else "observed"
    )
    with case.sessions() as session, session.begin():
        if mode == "cycle":
            session.execute(
                text(
                    "UPDATE content_threads SET parent_content_id=:reply,root_content_id=NULL,"
                    "parent_relation_status='observed' WHERE owner_id=:owner AND content_id=:root"
                ),
                {"reply": reply, "owner": case.owner_id, "root": case.comment_id},
            )
        else:
            session.execute(
                text("DELETE FROM content_threads WHERE owner_id=:owner AND content_id=:parent"),
                {"owner": case.owner_id, "parent": case.comment_id},
            )
    context = _scopes(case)[reply][1].prompt_items[0].comment_context
    assert context.parent_state == expected and context.next_parent_id is not None
    assert len(context.parents) == (1 if mode == "cycle" else 0)


def test_scan_cursor_bounds_unreadable_history_and_reaches_later_comments(
    analysis_case, monkeypatch
):
    import analysis.comments as comments
    from analysis.models import CommentAnalysisScanCursor

    case = analysis_case
    with case.sessions() as session, session.begin():
        rows = [
            {
                "id": UUID(int=i),
                "owner": case.owner_id,
                "post": case.content_id,
                "external": str(i),
                "now": case.now,
            }
            for i in range(1, 551)
        ]
        session.execute(
            text(
                "INSERT INTO content_records "
                "(id,owner_id,source_key,object_type,external_id,created_at) "
                "VALUES (:id,:owner,'hackernews','comment',:external,:now)"
            ),
            rows,
        )
        session.execute(
            text(
                "INSERT INTO content_threads "
                "(owner_id,content_id,post_content_id,root_content_id,"
                "parent_relation_status,created_at) "
                "VALUES (:owner,:id,:post,:id,'root',:now)"
            ),
            rows,
        )
    original = comments.load_comment_analysis_page_in_transaction
    reads = []

    def page(*args, **kwargs):
        reads.append(kwargs["after"])
        return original(*args, **kwargs)

    monkeypatch.setattr(comments, "load_comment_analysis_page_in_transaction", page)
    assert _scan(case) == () and len(reads) == 10
    with case.sessions() as session:
        cursor = session.get(CommentAnalysisScanCursor, (case.owner_id, case.topic_id))
        assert cursor.after_comment_id == UUID(int=500)
    assert len(_scan(case)) == 1 and len(reads) == 12


def test_comment_results_do_not_create_post_alert_facts_or_post_prompt_denominators(
    analysis_case, monkeypatch
):
    from analysis.alert_reading import load_negative_alert_facts_in_transaction
    from analysis.services import _load_prompt_versions_in_transaction

    case = analysis_case
    job, scope = _scopes(case)[case.comment_id]
    client = ControlledCommentClient()
    client.output = {
        "items": [
            {
                "content_version_id": str(scope.content_version_ids[0]),
                "state": "valid",
                "relevant": True,
                "relevance_reason": "评论自己的判断",
                "summary": "摘要",
            }
        ]
    }
    _executor(case, monkeypatch, client).execute(_message(case, job))
    with case.sessions() as session, session.begin():
        facts = load_negative_alert_facts_in_transaction(
            session,
            owner_id=case.owner_id,
            topic_id=case.topic_id,
            topic_rule_version=1,
            start=case.now - timedelta(days=10),
            end=case.now + timedelta(seconds=1),
            now=case.now,
        )
        assert (
            facts.value is None
            and facts.reason == "alert_sentiment_missing"
            and facts.manifest == {}
        )
        versions = _load_prompt_versions_in_transaction(
            session,
            owner_id=case.owner_id,
            end=case.now + timedelta(seconds=1),
            cutoff_at=case.now,
            runtime_windows=(),
        )
        assert COMMENT_ANALYSIS_PROMPT_VERSION not in versions


def test_unknown_target_and_unknown_ancestor_stay_unresolved(analysis_case):
    case = analysis_case
    unknown = _reply(case, None, status="unresolved")
    child = _reply(case, unknown)
    contexts = _scopes(case)
    assert contexts[unknown][1].prompt_items[0].comment_context.parent_state == "unresolved"
    context = contexts[child][1].prompt_items[0].comment_context
    assert context.parent_state == "unresolved"
    assert [item.content_id for item in context.parents] == [unknown]
