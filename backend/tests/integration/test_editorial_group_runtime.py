import json
from datetime import timedelta
from uuid import uuid4, uuid5

import httpx
import pytest
from sqlalchemy import text
from tests.integration.test_codex_execution import _runtime_setup
from tests.integration.test_codex_resets import engine as engine

from connections.editorial_group import begin_editorial_group_runs_in_transaction
from connections.editorial_schemas import (
    EditorialGroupBacklogExpected,
    EditorialGroupBacklogReviewInput,
    EditorialProfileInput,
)
from connections.editorial_services import EditorialSourceService
from core.config import Settings
from core.errors import ApplicationError
from jobs.editorial_budgets import (
    EditorialGroupBudgetRequest,
    reserve_editorial_group_budgets_in_transaction,
)
from jobs.editorial_member import load_editorial_group_manifest_in_transaction
from jobs.execution import JobExecutionFailure, JobExecutionService, MessageReference
from jobs.schemas import (
    BudgetContext,
    BudgetMetric,
    BudgetPolicyInput,
    JobAcceptedMessage,
    UsageAttemptInput,
    UsageKind,
    XApiPostReadCost,
)
from jobs.services import ResourceBudgetService
from sources.editorial_group_job import EditorialXGroupJobExecutor
from sources.editorial_schedule import enqueue_due_editorial_sources_in_transaction
from sources.editorial_schemas import EditorialCursor, EditorialSourceConfiguration


def test_group_zero_supplier_fee_gate_stops_before_outbound_request(engine):
    sessions, _owner, _profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    calls = []
    executor = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        clock=lambda: now,
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, json={})
        ),
    )
    with pytest.raises(JobExecutionFailure) as caught:
        executor.execute(message, lease)
    assert caught.value.error_code == "free_only_paid_source"
    assert calls == []
    with sessions() as session, session.begin():
        assert session.scalar(text("SELECT count(*) FROM content_records")) == 0
        assert session.scalar(text("SELECT count(*) FROM editorial_source_runs")) == 0


def group_setup(engine):
    sessions, owner, monitor, _message, _lease, now = _runtime_setup(engine)
    profiles = []
    low = str((int((now - timedelta(hours=1)).timestamp() * 1000) - 1288834974657) << 22)
    with sessions() as s:
        service = EditorialSourceService(s, clock=lambda: now)
        for handle in ("one", "two"):
            command = EditorialProfileInput(
                operation_id=uuid4(),
                name=handle,
                reason="controlled group",
                policy_version=1,
                connection_id=monitor.configuration.connection_id,
                connection_version=1,
                configuration=EditorialSourceConfiguration(kind="x_search", query=f"from:{handle}"),
            )
            p = service.save_profile(owner_id=owner, command=command)
            policy = uuid4()
            fields = {
                k: "controlled"
                for k in (
                    "object_type",
                    "external_id",
                    "identity_basis",
                    "canonical_url",
                    "author_name",
                    "published_at",
                    "text_scope",
                    "text_origin",
                    "title",
                    "body",
                )
            }
            with s.begin():
                s.execute(
                    text(
                        "INSERT INTO source_access_policies "
                        "(id,owner_id,source_key,capability,status,enabled,access_basis,terms_reference,component_name,component_version,component_license,processing_purpose,field_purposes,reviewed_at,policy_version,created_at,updated_at)"
                        " VALUES "
                        "(:id,:owner,:key,'search','approved',true,'official_api','https://example.com/terms','official-x','controlled','MIT','Controlled"
                        " group',CAST(:fields AS jsonb),:now,1,:now,:now)"
                    ),
                    dict(
                        id=policy, owner=owner, key=p.source_key, fields=json.dumps(fields), now=now
                    ),
                )
                s.execute(
                    text(
                        "INSERT INTO evidence_retention_policies "
                        "(id,owner_id,source_policy_id,source_policy_version,data_class,requested_days,effective_days,policy_version,created_at,updated_at)"
                        " VALUES (:id,:owner,:policy,1,'structured',30,30,1,:now,:now)"
                    ),
                    dict(id=uuid4(), owner=owner, policy=policy, now=now),
                )
            p = service.save_profile(
                owner_id=owner,
                profile_id=p.id,
                command=command.model_copy(
                    update={
                        "operation_id": uuid4(),
                        "expected_revision": p.revision,
                        "enabled": True,
                    }
                ),
            )
            with s.begin():
                s.execute(
                    text(
                        "UPDATE editorial_source_profiles SET cursor=CAST(:cursor AS "
                        "jsonb),next_fetch_at=:now WHERE id=:id"
                    ),
                    dict(
                        id=p.id,
                        now=now,
                        cursor=EditorialCursor(
                            initialized_at=now - timedelta(hours=1),
                            last_tweet_id=low,
                            last_ok_at=now - timedelta(hours=1),
                        ).model_dump_json(),
                    ),
                )
            profiles.append(p)
            ResourceBudgetService(s, clock=lambda: now).save_budget_policy(
                owner_id=owner,
                command=BudgetPolicyInput(
                    budget_key=f"group.member.{handle}",
                    metric=BudgetMetric.PROVIDER_USD_MICROS,
                    scope_kind="source",
                    scope_reference=p.source_key,
                    limit_units=1000000,
                    window_seconds=3600,
                    window_anchor_at=now - timedelta(minutes=1),
                    enabled=True,
                ),
            )
    return sessions, owner, profiles, now


def test_actual_scheduler_group_job_official_one_http_two_source_facts_and_exact_clocks(engine):
    sessions, owner, profiles, now = group_setup(engine)
    with sessions() as s:
        with s.begin():
            assert enqueue_due_editorial_sources_in_transaction(s, now, enabled=True) == 1
        with s.begin():
            out = s.execute(
                text(
                    "SELECT o.id,o.event_type,o.payload FROM outbox_messages o JOIN jobs j ON "
                    "j.id=o.aggregate_id WHERE j.kind='source.editorial.x_group'"
                )
            ).one()
        message = JobAcceptedMessage.model_validate(
            {**out.payload, "message_id": out.id, "event_type": out.event_type, "schema_version": 2}
        )
        lease = JobExecutionService(s, lease_seconds=30, clock=lambda: now).acquire(
            job_id=message.job_id, worker_id="controlled-group"
        )
    calls = []
    high = (int(now.timestamp() * 1000) - 1288834974657) << 22

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": str(high + i),
                        "author_id": str(i),
                        "text": f"{name} actual update",
                        "created_at": now.isoformat(),
                    }
                    for i, name in ((1, "one"), (2, "two"))
                ],
                "includes": {
                    "users": [{"id": "1", "username": "one"}, {"id": "2", "username": "two"}]
                },
            },
        )

    settings = Settings(
        _env_file=None,
        database_url=engine.url.render_as_string(hide_password=False),
        environment="test",
        editorial_sources_enabled=True,
        editorial_x_authorized=True,
        editorial_x_token="controlled",
        editorial_x_post_unit_usd_micros=10,
    )
    result = EditorialXGroupJobExecutor(
        sessions,
        settings,
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(handler),
    ).execute(message, lease)
    assert result.status == "succeeded" and len(calls) == 1
    with sessions() as s, s.begin():
        rows = s.execute(text("SELECT source_key FROM content_records")).scalars().all()
        assert set(rows) == {p.source_key for p in profiles}
        assert (
            s.scalar(text("SELECT count(*) FROM editorial_source_runs WHERE status='succeeded'"))
            == 2
        )
        assert (
            s.scalar(
                text("SELECT count(*) FROM evidence_resources WHERE owner_id=:owner"),
                dict(owner=owner),
            )
            >= 2
        )
        assert (
            s.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w JOIN "
                    "resource_budget_policies p ON p.id=w.budget_policy_id WHERE "
                    "p.metric='network_request' AND p.scope_kind='global'"
                )
            )
            == 1
        )
        assert (
            s.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w JOIN "
                    "resource_budget_policies p ON p.id=w.budget_policy_id WHERE "
                    "p.metric='x_api_usd_micros' AND p.scope_kind='global'"
                )
            )
            == 20
        )
        assert (
            s.scalar(
                text("SELECT count(*) FROM resource_usage_attempts WHERE operation_id=:op"),
                dict(op=message.operation_id),
            )
            == 1
        )
        assert all(
            EditorialCursor.model_validate_json(c).last_ok_at == now
            for c in s.execute(text("SELECT cursor::text FROM editorial_source_profiles")).scalars()
        )


def admitted_group(sessions, now):
    with sessions() as s:
        with s.begin():
            assert enqueue_due_editorial_sources_in_transaction(s, now, enabled=True) == 1
        with s.begin():
            out = s.execute(
                text(
                    "SELECT o.id,o.event_type,o.payload FROM outbox_messages o "
                    "JOIN jobs j ON j.id=o.aggregate_id "
                    "WHERE j.kind='source.editorial.x_group' ORDER BY j.created_at DESC LIMIT 1"
                )
            ).one()
        message = JobAcceptedMessage.model_validate(
            {**out.payload, "message_id": out.id, "event_type": out.event_type, "schema_version": 2}
        )
        lease = JobExecutionService(s, lease_seconds=30, clock=lambda: now).acquire(
            job_id=message.job_id, worker_id="controlled-group"
        )
    return message, lease


def controlled_settings(engine, *, price=10, authorized=True):
    return Settings(
        _env_file=None,
        database_url=engine.url.render_as_string(hide_password=False),
        environment="test",
        editorial_sources_enabled=True,
        editorial_x_authorized=authorized,
        editorial_x_token="controlled",
        editorial_x_post_unit_usd_micros=price,
    )


def official_answer(now, *, token=None):
    high = (int(now.timestamp() * 1000) - 1288834974657) << 22
    answer = {
        "data": [
            {
                "id": str(high + i),
                "author_id": str(i),
                "text": f"{name} actual update",
                "created_at": now.isoformat(),
            }
            for i, name in ((1, "one"), (2, "two"))
        ],
        "includes": {"users": [{"id": "1", "username": "one"}, {"id": "2", "username": "two"}]},
    }
    if token:
        answer["meta"] = {"next_token": token}
    return answer


def complete_group(sessions, message, lease, result, now):
    with sessions() as s:
        JobExecutionService(s, lease_seconds=30, clock=lambda: now).complete(
            lease,
            message=MessageReference(message.message_id, "controlled", 0, 0),
            completion=result,
        )


def test_group_partial_gap_resumes_original_frozen_query_after_restart_and_has_own_clocks(engine):
    sessions, _owner, _profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    first = []

    def first_handler(request):
        first.append(request)
        answer = official_answer(now, token=f"next-{len(first)}")
        answer["data"] = answer["data"][:1]
        return httpx.Response(200, json=answer)

    result = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(first_handler),
    ).execute(message, lease)
    assert result.status == "partially_succeeded" and len(first) == 10
    complete_group(sessions, message, lease, result, now)
    with sessions() as s, s.begin():
        cursors = tuple(
            EditorialCursor.model_validate_json(c)
            for c in s.execute(text("SELECT cursor::text FROM editorial_source_profiles")).scalars()
        )
        assert all(c.last_ok_at == now - timedelta(hours=1) for c in cursors)
        assert all(c.x_backlog[0].next_token == "next-10" for c in cursors)
        old_query = cursors[0].x_backlog[0].query
        stop = cursors[0].x_backlog[0].stop_at_id
        assert (
            s.scalar(text("SELECT count(*) FROM editorial_source_runs WHERE status='partial'")) == 2
        )
    later = now + timedelta(minutes=60)
    resumed, resumed_lease = admitted_group(sessions, later)
    assert resumed.job_id != message.job_id
    requests = []
    completion = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: later,
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={"data": []})
        ),
    ).execute(resumed, resumed_lease)
    assert completion.status == "succeeded" and len(requests) == 2
    assert requests[1].url.params["next_token"] == "next-10"
    assert requests[1].url.params["query"] == old_query
    assert requests[1].url.params["since_id"] == stop
    with sessions() as s, s.begin():
        final = tuple(
            EditorialCursor.model_validate_json(c)
            for c in s.execute(text("SELECT cursor::text FROM editorial_source_profiles")).scalars()
        )
        assert all(c.last_ok_at == later and not c.x_backlog for c in final)
        assert s.scalar(text("SELECT count(*) FROM content_records WHERE source_key='x'")) == 0
        assert s.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 12


def test_group_member_revoke_between_http_pages_stops_every_member_commit(engine):
    sessions, _owner, profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    requests = []

    def handler(request):
        requests.append(request)
        with sessions() as s, s.begin():
            s.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE source_key=:key"),
                dict(key=profiles[0].source_key),
            )
        return httpx.Response(200, json=official_answer(now, token="more"))

    result = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(handler),
    ).execute(message, lease)
    assert result.status == "partially_succeeded" and len(requests) == 1
    with sessions() as s, s.begin():
        assert s.scalar(text("SELECT count(*) FROM content_records")) == 0
        assert (
            s.scalar(text("SELECT count(*) FROM editorial_source_runs WHERE status='unknown'")) == 2
        )
        assert all(
            EditorialCursor.model_validate_json(c).last_ok_at == now - timedelta(hours=1)
            for c in s.execute(text("SELECT cursor::text FROM editorial_source_profiles")).scalars()
        )
        assert s.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 1
        assert (
            s.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.metric='x_api_usd_micros' AND p.scope_kind='global'"
                )
            )
            == 20
        )


def test_group_running_request_recovery_settles_original_caps_and_never_reissues_http(engine):
    sessions, owner, _profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    with sessions() as s, s.begin():
        manifest = load_editorial_group_manifest_in_transaction(
            s, owner_id=owner, job_id=message.job_id
        )
        begin_editorial_group_runs_in_transaction(
            s,
            manifest=manifest,
            job_id=message.job_id,
            operation_id=message.operation_id,
            guard=None,
            now=now,
        )
        request = EditorialGroupBudgetRequest(
            operation_id=message.operation_id,
            reservation_id=uuid5(message.job_id, "group-request:1"),
            context=BudgetContext(
                source_ref="x",
                connection_ref=str(manifest.connection_id),
                job_ref=str(message.job_id),
            ),
            member_sources=tuple(m.source_key for m in manifest.members),
            manifest_sha256=manifest.sha256,
            quote=XApiPostReadCost(max_posts=100, unit_price_usd_micros=10),
        )
        reserve_editorial_group_budgets_in_transaction(s, owner_id=owner, command=request, now=now)
        ResourceBudgetService(s, clock=lambda: now).begin_attempt_in_transaction(
            owner_id=owner,
            command=UsageAttemptInput(
                attempt_id=uuid5(request.reservation_id, "usage"),
                operation_id=message.operation_id,
                component_key="collector.editorial",
                usage_kind=UsageKind.NETWORK_REQUEST,
                stage="source_group_request",
                started_at=now,
            ),
        )
        JobExecutionService(s, lease_seconds=30, clock=lambda: now).begin_request_in_transaction(
            lease
        )
    later = now + timedelta(seconds=31)
    with sessions() as s:
        recovery_lease = JobExecutionService(s, lease_seconds=30, clock=lambda: later).acquire(
            job_id=message.job_id, worker_id="controlled-recovery"
        )
    requests = []
    executor = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine, price=20),
        zero_supplier_fee_only=False,
        clock=lambda: later,
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={"data": []})
        ),
    )
    result = executor.execute(message, recovery_lease)
    again = executor.execute(message, recovery_lease)
    assert result.status == again.status == "partially_succeeded" and not requests
    with sessions() as s, s.begin():
        assert (
            s.scalar(text("SELECT count(*) FROM editorial_source_runs WHERE status='unknown'")) == 2
        )
        assert s.scalar(text("SELECT count(*) FROM content_records")) == 0
        assert (
            s.scalar(
                text("SELECT count(*) FROM resource_budget_reservations WHERE status='reserved'")
            )
            == 0
        )
        assert s.scalar(text("SELECT outcome FROM resource_usage_attempts")) == "failed"
        assert (
            s.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.metric='x_api_usd_micros' AND p.scope_kind='global'"
                )
            )
            == 1000
        )
        assert (
            s.scalar(
                text(
                    "SELECT sum(used_units) FROM resource_budget_windows w "
                    "JOIN resource_budget_policies p ON p.id=w.budget_policy_id "
                    "WHERE p.metric='provider_usd_micros' AND p.scope_kind='source'"
                )
            )
            == 2000
        )


def test_group_blocked_window_has_new_job_next_due_without_reusing_old_manifest(engine):
    sessions, _owner, _profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    requests = []
    executor = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine, authorized=False),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={"data": []})
        ),
    )
    completion = executor.execute(message, lease)
    assert completion.status == "partially_succeeded" and not requests
    complete_group(sessions, message, lease, completion, now)
    later = now + timedelta(hours=1)
    next_message, _next_lease = admitted_group(sessions, later)
    assert next_message.job_id != message.job_id
    assert next_message.configuration_ref != message.configuration_ref


def test_group_unknown_http_has_durable_receipts_and_no_replay_or_watermark(engine):
    sessions, _owner, _profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    requests = []

    def unknown(request):
        requests.append(request)
        raise httpx.ReadTimeout("controlled timeout", request=request)

    executor = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(unknown),
    )
    first = executor.execute(message, lease)
    second = executor.execute(message, lease)
    assert first.status == second.status == "partially_succeeded" and len(requests) == 1
    with sessions() as s, s.begin():
        assert (
            s.scalar(text("SELECT count(*) FROM editorial_source_runs WHERE status='unknown'")) == 2
        )
        assert s.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 1
        assert s.scalar(text("SELECT outcome FROM resource_usage_attempts")) == "failed"
        assert s.scalar(text("SELECT count(*) FROM content_records")) == 0
        assert all(
            EditorialCursor.model_validate_json(c).last_ok_at == now - timedelta(hours=1)
            for c in s.execute(text("SELECT cursor::text FROM editorial_source_profiles")).scalars()
        )


def test_group_missing_member_spend_policy_is_zero_http_atomic_budget_block(engine):
    sessions, _owner, profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    with sessions() as s, s.begin():
        s.execute(
            text(
                "UPDATE resource_budget_policies SET enabled=false "
                "WHERE metric='provider_usd_micros' AND scope_reference=:key"
            ),
            dict(key=profiles[0].source_key),
        )
    requests = []
    result = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={"data": []})
        ),
    ).execute(message, lease)
    assert result.status == "partially_succeeded" and not requests
    with sessions() as s, s.begin():
        assert s.scalar(text("SELECT count(*) FROM resource_budget_reservations")) == 0
        assert s.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0
        assert (
            s.scalar(text("SELECT count(*) FROM editorial_source_runs WHERE status='blocked'")) == 2
        )


def test_group_changed_configuration_before_execution_rejects_every_member_and_request(engine):
    sessions, owner, profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    with sessions() as s:
        service = EditorialSourceService(s, clock=lambda: now)
        current = service.get_profile(owner_id=owner, profile_id=profiles[0].id)
        service.save_profile(
            owner_id=owner,
            profile_id=current.id,
            command=EditorialProfileInput(
                operation_id=uuid4(),
                name=current.name,
                reason="controlled stale Job",
                expected_revision=current.revision,
                enabled=True,
                policy_version=1,
                connection_id=current.connection_id,
                connection_version=current.connection_version,
                configuration=current.configuration.model_copy(update={"query": "from:changed"}),
            ),
        )
    requests = []
    result = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={"data": []})
        ),
    ).execute(message, lease)
    assert result.status == "partially_succeeded" and not requests
    with sessions() as s, s.begin():
        assert s.scalar(text("SELECT count(*) FROM editorial_source_runs")) == 0
        assert s.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0
        assert s.scalar(text("SELECT count(*) FROM content_records")) == 0


def test_group_configured_gap_requires_all_member_cas_and_operator_restart_keeps_old_clock(engine):
    sessions, owner, profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    requests = []
    result = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(
            lambda request: (
                requests.append(request)
                or httpx.Response(200, json=official_answer(now, token=f"next-{len(requests)}"))
            )
        ),
    ).execute(message, lease)
    complete_group(sessions, message, lease, result, now)
    with sessions() as s:
        service = EditorialSourceService(s, clock=lambda: now)
        original = service.list_group_backlogs(owner_id=owner)[0]
        changed = service.get_profile(owner_id=owner, profile_id=profiles[0].id)
        changed = service.save_profile(
            owner_id=owner,
            profile_id=changed.id,
            command=EditorialProfileInput(
                operation_id=uuid4(),
                name=changed.name,
                reason="Controlled changed query",
                expected_revision=changed.revision,
                enabled=True,
                policy_version=1,
                connection_id=changed.connection_id,
                connection_version=changed.connection_version,
                configuration=changed.configuration.model_copy(update={"query": "from:changed"}),
            ),
        )
        blocked = service.list_group_backlogs(owner_id=owner)[0]
        assert blocked.state == "blocked_configuration"
        command = EditorialGroupBacklogReviewInput(
            operation_id=uuid4(),
            group_sha256=original.group_sha256,
            actor="Controlled operator",
            reason="Restart original members from saved low watermark after reviewed query change",
            action="restart_from_saved_watermark",
            expected_members=tuple(
                EditorialGroupBacklogExpected(
                    profile_id=m.profile_id,
                    configuration_version=m.configuration_version,
                    revision=m.revision,
                )
                for m in blocked.members
            ),
        )
        stale = command.model_copy(
            update={
                "operation_id": uuid4(),
                "expected_members": tuple(
                    m.model_copy(update={"revision": m.revision - 1})
                    for m in command.expected_members
                ),
            }
        )
        with pytest.raises(ApplicationError):
            service.review_group_backlog(owner_id=owner, command=stale)
        with s.begin():
            assert (
                s.scalar(
                    text("SELECT count(*) FROM operations_audit_operations WHERE operation_id=:id"),
                    dict(id=stale.operation_id),
                )
                == 0
            )
        reviewed = service.review_group_backlog(owner_id=owner, command=command)
        assert reviewed == service.review_group_backlog(owner_id=owner, command=command)
        assert not service.list_group_backlogs(owner_id=owner)
        with s.begin():
            cursors = tuple(
                EditorialCursor.model_validate_json(c)
                for c in s.execute(
                    text("SELECT cursor::text FROM editorial_source_profiles")
                ).scalars()
            )
            assert all(c.last_ok_at == now - timedelta(hours=1) for c in cursors)
            assert all(not c.x_backlog for c in cursors)
            low = str((int((now - timedelta(hours=1)).timestamp() * 1000) - 1288834974657) << 22)
            assert all(c.last_tweet_id == low for c in cursors)
            assert (
                s.scalar(
                    text("SELECT status FROM operations_audit_operations WHERE operation_id=:id"),
                    dict(id=command.operation_id),
                )
                == "succeeded"
            )
