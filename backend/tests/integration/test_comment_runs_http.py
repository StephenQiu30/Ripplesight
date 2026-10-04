from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.conftest import authenticated_owner_id
from tests.integration.test_monitor_topics import _csrf_headers
from tests.integration.test_topic_runs import _ready_topic
from tests.integration.test_topic_runs import monitor_topic_client as _topic_client  # noqa: F401

from connections.schemas import SourceEntryPoint
from content.comments import CommentManualRunService
from content.comments_execution import CommentsExecutor
from content.schemas import CommentManualRunInput, PersistContentPostInput
from content.services import ContentService
from core.errors import ApplicationError
from evidence.schemas import AdmittedSourcePayload, DataClass
from jobs.execution import JobExecutionService, MessageReference
from jobs.models import Job
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    JobAcceptedMessage,
    JobStatus,
)
from jobs.services import ResourceBudgetService
from sources.adapters.hackernews import HackerNewsAdapter
from sources.contracts import (
    CommentsRequest,
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourceSort,
    SourceTerminalEvidence,
)


def _seed_old_hn_post(client: TestClient) -> UUID:
    topic_location = _ready_topic(client, source_keys=("hackernews",))
    search = client.post(
        f"{topic_location}/runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4()), "source_keys": ["hackernews"]},
    )
    assert search.status_code == 202, search.json()
    job_id = UUID(search.json()["sources"][0]["job_ids"][0])
    now = datetime.now(UTC)
    factory = client.app.state.session_factory
    with factory() as session:
        owner_id = authenticated_owner_id(session)
        connection_id, connection_version = session.execute(
            text(
                "SELECT id, current_version FROM source_connections WHERE source_key = 'hackernews'"
            )
        ).one()
        policy_id, policy_version = session.execute(
            text(
                "SELECT id, policy_version FROM source_access_policies "
                "WHERE source_key = 'hackernews' AND capability = 'search'"
            )
        ).one()
        retention_id, retention_version, retention_days = session.execute(
            text(
                "SELECT id, policy_version, effective_days FROM evidence_retention_policies "
                "WHERE source_policy_id = :policy_id AND data_class = 'structured'"
            ),
            {"policy_id": policy_id},
        ).one()
        created = ContentService(session).persist_post(
            owner_id=owner_id,
            command=PersistContentPostInput(
                job_id=job_id,
                source_operation_id=uuid4(),
                connection_id=connection_id,
                connection_version=connection_version,
                entry_point=SourceEntryPoint.MANUAL,
                component_name="collector.hackernews",
                component_version="hn-algolia-v1",
                admission=AdmittedSourcePayload(
                    policy_id=policy_id,
                    policy_version=policy_version,
                    owner_id=owner_id,
                    source_key="hackernews",
                    capability=SourceCapability.SEARCH,
                    retention_policy_id=retention_id,
                    retention_policy_version=retention_version,
                    data_class=DataClass.STRUCTURED,
                    collected_at=now,
                    expires_at=now + timedelta(days=retention_days),
                    fields={
                        "object_type": "post",
                        "external_id": "123456",
                        "canonical_url": "https://news.ycombinator.com/item?id=123456",
                        "author_external_id": "hn-author",
                        "published_at": (now - timedelta(days=3)).isoformat(),
                        "like_count": 100,
                        "comment_count": 42,
                        "repost_count": None,
                        "view_count": None,
                        "play_count": None,
                        "danmaku_count": None,
                        "text_scope": "full",
                        "text_origin": "source",
                        "title": "Brand 召回 old HN story",
                        "body": "Brand 召回 discussion",
                    },
                ),
            ),
        )
    with factory.begin() as session:
        ResourceBudgetService(session, clock=lambda: now).save_budget_policy_in_transaction(
            owner_id=owner_id,
            command=BudgetPolicyInput(
                budget_key="global.plan038.comments.daily",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                scope_reference=None,
                limit_units=10,
                window_seconds=86_400,
                window_anchor_at=datetime(2026, 1, 1, tzinfo=UTC),
                enabled=True,
            ),
        )
        session.execute(
            text("UPDATE content_records SET created_at = :old WHERE id = :id"),
            {"old": now - timedelta(days=3), "id": created.id},
        )
    return created.id


def test_old_hn_post_manual_comments_are_accepted_once(request: pytest.FixtureRequest) -> None:
    monitor_topic_client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(monitor_topic_client)
    route = f"/api/contents/{content_id}/comment-runs"
    payload = {"operation_id": str(uuid4())}
    assert monitor_topic_client.get(f"/api/contents/{content_id}").status_code == 200
    with monitor_topic_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs WHERE kind = 'source.comments'")) == 0
    assert monitor_topic_client.post(route, json=payload).status_code == 403
    first = monitor_topic_client.post(
        route, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    with monitor_topic_client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
    replay = monitor_topic_client.post(
        route, headers=_csrf_headers(monitor_topic_client), json=payload
    )
    assert first.status_code == 202, first.json()
    assert replay.status_code == 200, replay.json()
    assert first.json() == replay.json()
    with monitor_topic_client.app.state.session_factory() as session:
        rows = session.execute(
            text(
                "SELECT scope, configuration_ref, configuration_version "
                "FROM jobs WHERE kind = 'source.comments'"
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].scope["post_external_id"] == "123456"
        assert rows[0].scope["entry_point"] == "manual"
        assert rows[0].configuration_ref.startswith("topic:")
        assert rows[0].configuration_version == 1
        assert session.scalar(text("SELECT count(*) FROM outbox_messages")) == 2


def test_comments_without_global_budget_do_not_accept_an_outbound_job(
    request: pytest.FixtureRequest,
) -> None:
    client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(client)
    with client.app.state.session_factory.begin() as session:
        session.execute(text("DELETE FROM resource_budget_policies WHERE scope_kind = 'global'"))
    readiness = client.get(f"/api/contents/{content_id}/comment-run-readiness")
    assert readiness.json() == {
        "supported": True,
        "available": False,
        "reason": "comments_budget_exhausted",
    }
    rejected = client.post(
        f"/api/contents/{content_id}/comment-runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4())},
    )
    assert rejected.status_code == 409
    with client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs WHERE kind = 'source.comments'")) == 0


def test_comment_refresh_readiness_is_read_only_and_tracks_admission(
    request: pytest.FixtureRequest,
) -> None:
    client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(client)
    route = f"/api/contents/{content_id}/comment-run-readiness"
    assert client.get(f"/api/contents/{uuid4()}/comment-run-readiness").status_code == 404
    ready = client.get(route)
    assert ready.status_code == 200, ready.json()
    assert ready.json() == {"supported": True, "available": True, "reason": None}
    with client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM jobs WHERE kind = 'source.comments'")) == 0
        with pytest.raises(ApplicationError, match="resource_not_found"):
            CommentManualRunService(session).readiness(owner_id=uuid4(), content_id=content_id)
    with client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
    assert client.get(route).json() == {
        "supported": True,
        "available": False,
        "reason": "comments_budget_exhausted",
    }
    with client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = true "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
    accepted = client.post(
        f"/api/contents/{content_id}/comment-runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4())},
    )
    assert accepted.status_code == 202, accepted.json()
    assert client.get(route).json() == {
        "supported": True,
        "available": False,
        "reason": "comments_rate_limited",
    }
    with client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE source_access_policies SET enabled = false "
                "WHERE source_key = 'hackernews' AND capability = 'comments'"
            )
        )
    assert client.get(route).json() == {
        "supported": False,
        "available": False,
        "reason": "comments_not_ready",
    }


def test_manual_comments_reject_unknown_content_and_frequency(
    request: pytest.FixtureRequest,
) -> None:
    monitor_topic_client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(monitor_topic_client)
    headers = _csrf_headers(monitor_topic_client)
    unknown = monitor_topic_client.post(
        f"/api/contents/{uuid4()}/comment-runs",
        headers=headers,
        json={"operation_id": str(uuid4())},
    )
    assert unknown.status_code == 404
    route = f"/api/contents/{content_id}/comment-runs"
    first = monitor_topic_client.post(route, headers=headers, json={"operation_id": str(uuid4())})
    assert first.status_code == 202, first.json()
    limited = monitor_topic_client.post(route, headers=headers, json={"operation_id": str(uuid4())})
    assert limited.status_code == 409
    assert limited.json()["code"] == "comments_rate_limited"
    with (
        monitor_topic_client.app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="resource_not_found"),
    ):
        CommentManualRunService(session).run(
            owner_id=uuid4(),
            content_id=content_id,
            command=CommentManualRunInput(operation_id=uuid4()),
        )


def test_manual_comments_require_budget_and_comment_capability(
    request: pytest.FixtureRequest,
) -> None:
    monitor_topic_client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(monitor_topic_client)
    route = f"/api/contents/{content_id}/comment-runs"
    headers = _csrf_headers(monitor_topic_client)
    with monitor_topic_client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
    budget = monitor_topic_client.post(route, headers=headers, json={"operation_id": str(uuid4())})
    assert budget.status_code == 409
    assert budget.json()["code"] == "comments_budget_exhausted"
    with monitor_topic_client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = true "
                "WHERE budget_key = 'source.hackernews.network.daily'"
            )
        )
        session.execute(
            text(
                "UPDATE source_access_policies SET enabled = false "
                "WHERE source_key = 'hackernews' AND capability = 'comments'"
            )
        )
    capability = monitor_topic_client.post(
        route, headers=headers, json={"operation_id": str(uuid4())}
    )
    assert capability.status_code == 409
    assert capability.json()["code"] == "comments_not_ready"


def _execute_manual_comments(
    client: TestClient,
    *,
    job_id: UUID,
    now: datetime,
    comment_children: list[dict[str, object]],
    offset: int,
    expected_status: JobStatus = JobStatus.PARTIALLY_SUCCEEDED,
    terminal_proof: str = "missing",
) -> tuple[str, ...]:
    factory = client.app.state.session_factory
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        message = JobAcceptedMessage(
            schema_version=2,
            message_id=uuid4(),
            event_type="job.accepted.v2",
            job_id=job.id,
            owner_id=job.owner_id,
            operation_id=job.operation_id,
            kind=job.kind,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
            source_key=job.source_key,
            source_capability=SourceCapability.COMMENTS,
        )
        starts_at = datetime.fromisoformat(job.scope["starts_at"])
        ends_at = datetime.fromisoformat(job.scope["ends_at"])
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=75, clock=lambda: now).acquire(
            job_id=job_id, worker_id="comments-integration"
        )
    requested: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert request.url.path == "/api/v1/items/123456"
        return httpx.Response(200, json={"id": 123456, "children": comment_children})

    class TailEvidenceAdapter(HackerNewsAdapter):
        def _comments(self, request: CommentsRequest) -> SourcePage:
            # The executor and admission services share this frozen clock. A wall-clock
            # observation can move past it under load and become an invalid future sample.
            page = super()._comments(request).model_copy(update={"observed_at": now})
            if terminal_proof == "missing" or page.state is SourcePageState.MORE:
                return page
            return page.model_copy(
                update={
                    "terminal_evidence": SourceTerminalEvidence(
                        starts_at=(
                            starts_at - timedelta(seconds=1)
                            if terminal_proof == "mismatched"
                            else starts_at
                        ),
                        ends_at=ends_at,
                        sort_key=SourceSort.TOP,
                        query_bounded=terminal_proof != "unbounded",
                        sort_applied=True,
                        terminal_verified=True,
                    )
                }
            )

    executor = CommentsExecutor(
        factory,
        lease_seconds=75,
        clock=lambda: now,
        adapter_factory=lambda before, cancelled, max_requests, max_seconds: TailEvidenceAdapter(
            before_request=before,
            cancelled=cancelled,
            max_requests=max_requests,
            max_seconds=max_seconds,
            transport=httpx.MockTransport(respond),
        ),
    )
    renewed, completion = executor.execute(message, lease)
    assert completion.status is expected_status
    with factory() as session:
        JobExecutionService(session, lease_seconds=75, clock=lambda: now).complete(
            renewed,
            message=MessageReference(
                message_id=message.message_id,
                topic="hotkey.tests.comments",
                partition=0,
                offset=offset,
            ),
            completion=completion,
        )
    return tuple(requested)


@pytest.mark.parametrize(
    ("sample", "terminal_proof", "expected_reason"),
    [
        ("empty", "missing", "unverified_terminal"),
        ("root", "missing", "unverified_terminal"),
        ("root", "unbounded", "unverified_terminal"),
        ("root", "mismatched", "unverified_terminal"),
        ("roots_over_limit", "matching", "budget_exhausted"),
        ("replies_over_limit", "matching", "budget_exhausted"),
        ("earlier_page_over_limit", "matching", "budget_exhausted"),
        ("duplicate", "matching", None),
        ("root", "matching", None),
    ],
)
def test_comment_coverage_requires_source_proof_and_an_untruncated_sample(
    request: pytest.FixtureRequest,
    sample: str,
    terminal_proof: str,
    expected_reason: str | None,
) -> None:
    client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(client)
    accepted = client.post(
        f"/api/contents/{content_id}/comment-runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4())},
    )
    assert accepted.status_code == 202, accepted.json()
    job_id = UUID(accepted.json()["job_id"])
    root: dict[str, object] = {
        "type": "comment",
        "id": 987001,
        "author": "hn-reader",
        "text": "<p>root</p>",
        "created_at_i": int(datetime.now(UTC).timestamp()),
        "children": [],
    }
    children = [] if sample == "empty" else [root]
    if sample in {"roots_over_limit", "earlier_page_over_limit"}:
        children.extend([{**root, "id": 987002}, {**root, "id": 987003}])
    elif sample == "replies_over_limit":
        root["children"] = [{**root, "id": 987002}, {**root, "id": 987003}]
    elif sample == "duplicate":
        children.append(root)
    with client.app.state.session_factory.begin() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.scope = {
            **job.scope,
            "first_level_limit": 1,
            "replies_per_thread_limit": 1,
            "page_size": 1 if sample == "earlier_page_over_limit" else 100,
        }
    requested = _execute_manual_comments(
        client,
        job_id=job_id,
        now=datetime.now(UTC) + timedelta(seconds=1),
        comment_children=children,
        offset=0,
        expected_status=JobStatus.PARTIALLY_SUCCEEDED if expected_reason else JobStatus.SUCCEEDED,
        terminal_proof=terminal_proof,
    )
    assert len(requested) == 1
    with client.app.state.session_factory() as session:
        coverage = session.execute(
            text("SELECT status, stop_reason FROM coverage_windows WHERE last_job_id = :job_id"),
            {"job_id": job_id},
        ).one()
        assert coverage.status == ("partial" if expected_reason else "confirmed")
        assert coverage.stop_reason == expected_reason


def test_old_hn_root_is_revisited_and_new_reply_keeps_direct_parent(
    request: pytest.FixtureRequest,
) -> None:
    client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(client)
    now = datetime.now(UTC)
    route = f"/api/contents/{content_id}/comment-runs"
    first = client.post(
        route,
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4())},
    )
    assert first.status_code == 202, first.json()
    now = datetime.now(UTC) + timedelta(seconds=1)
    root = {
        "type": "comment",
        "id": 987001,
        "author": "hn-reader",
        "text": "<p>first root</p>",
        "created_at_i": int((now - timedelta(days=2)).timestamp()),
        "children": [],
    }
    first_requests = _execute_manual_comments(
        client,
        job_id=UUID(first.json()["job_id"]),
        now=now,
        comment_children=[root],
        offset=0,
    )
    assert len(first_requests) == 1

    next_round_at = now + timedelta(hours=6, minutes=1)
    with client.app.state.session_factory() as session:
        owner_id = authenticated_owner_id(session)
        accepted = CommentManualRunService(session, clock=lambda: next_round_at).run(
            owner_id=owner_id,
            content_id=content_id,
            command=CommentManualRunInput(operation_id=uuid4()),
        )
    reply = {
        "type": "comment",
        "id": 987002,
        "author": "hn-reader-2",
        "text": "<p>new reply</p>",
        "created_at_i": int((now + timedelta(minutes=1)).timestamp()),
        "children": [],
    }
    second_requests = _execute_manual_comments(
        client,
        job_id=accepted.job_id,
        now=next_round_at,
        comment_children=[{**root, "children": [reply]}],
        offset=1,
    )
    assert len(second_requests) == 1
    with client.app.state.session_factory() as session:
        rows = session.execute(
            text(
                "SELECT c.external_id, t.post_content_id, t.root_content_id, "
                "t.parent_content_id, t.reply_target_content_id, "
                "t.parent_relation_status, c.id "
                "FROM content_threads t JOIN content_records c ON c.id = t.content_id "
                "WHERE t.post_content_id = :post_id ORDER BY c.external_id"
            ),
            {"post_id": content_id},
        ).all()
        assert [(row.external_id, row.post_content_id) for row in rows] == [
            ("987001", content_id),
            ("987002", content_id),
        ]
        assert rows[0].parent_content_id is None
        assert rows[0].root_content_id == rows[0].id
        assert rows[0].reply_target_content_id is None
        assert rows[0].parent_relation_status == "root"
        assert rows[1].parent_content_id == rows[0].id
        assert rows[1].root_content_id == rows[0].id
        assert rows[1].reply_target_content_id == rows[0].id
        assert rows[1].parent_relation_status == "observed"
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM content_records WHERE source_key = 'hackernews' "
                    "AND object_type = 'comment'"
                )
            )
            == 2
        )
        assert session.scalar(text("SELECT count(*) FROM processed_messages")) == 2
        budget_usage = session.execute(
            text(
                "SELECT p.budget_key, sum(r.actual_units) FROM resource_budget_reservations r "
                "JOIN resource_budget_policies p ON p.id = r.budget_policy_id "
                "GROUP BY p.budget_key ORDER BY p.budget_key"
            )
        ).all()
        assert budget_usage == [
            ("global.plan038.comments.daily", 2),
            ("source.hackernews.network.daily", 2),
            ("test.network.daily", 2),
        ]
