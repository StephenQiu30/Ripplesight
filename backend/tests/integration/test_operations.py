# ruff: noqa: F811
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.integration.test_content_records import _user_scope
from tests.integration.test_event_reading import event_read_client  # noqa: F401

from core.errors import ApplicationError
from operations.models import Feedback, FeedbackCooldown, OperatorAuditOperation
from operations.schemas import DictionaryInput, FeedbackInput, FeedbackUpdateInput
from operations.services import OperationsService, record_process_heartbeat_in_transaction


def test_feedback_idempotence_and_cooldown_are_persistent_and_owner_scoped(
    event_read_client: TestClient,
):
    owner = _user_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    command = FeedbackInput(operation_id=uuid4(), content="需要更清楚的原文入口")
    now = datetime.now(UTC)
    with factory() as session:
        result = OperationsService(
            session, feedback_secret="controlled-test", clock=lambda: now
        ).submit_feedback(
            owner_id=owner, command=command, client_ip="192.0.2.20", user_agent="controlled"
        )
    with factory() as session:
        service = OperationsService(session, feedback_secret="controlled-test", clock=lambda: now)
        replay = service.submit_feedback(
            owner_id=owner, command=command, client_ip="192.0.2.20", user_agent="controlled"
        )
        assert replay.replayed and replay.id == result.id
        with pytest.raises(ApplicationError, match="feedback_rate_limited") as error:
            service.submit_feedback(
                owner_id=owner,
                command=FeedbackInput(operation_id=uuid4(), content="第二个反馈"),
                client_ip="192.0.2.20",
                user_agent="controlled",
            )
        assert error.value.context["retry_after"] == 60
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            service.submit_feedback(
                owner_id=owner,
                command=command.model_copy(update={"content": "另一份内容"}),
                client_ip="192.0.2.20",
                user_agent="controlled",
            )
    with factory() as session:
        row = session.scalar(select(FeedbackCooldown))
        assert len(row.source_hash) == 32
        assert "192.0.2.20" not in str(row.__dict__)
        assert OperationsService(session).list_feedback(owner_id=uuid4())[0] == []


def test_feedback_deletion_ban_and_audit_commit_atomically(event_read_client):
    owner = _user_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        result = OperationsService(session, feedback_secret="controlled-test").submit_feedback(
            owner_id=owner,
            command=FeedbackInput(
                operation_id=uuid4(), content="反馈正文不应复制到审计", email="private@example.test"
            ),
            client_ip="192.0.2.21",
            user_agent="controlled",
        )
    command = FeedbackUpdateInput(
        operation_id=uuid4(),
        expected_revision=1,
        reason="运营确认删除",
        status="deleted",
        banned=True,
    )
    with factory() as session:
        service = OperationsService(session)
        updated = service.update_feedback(owner_id=owner, feedback_id=result.id, command=command)
        assert updated.revision == 2
        assert service.update_feedback(
            owner_id=owner, feedback_id=result.id, command=command
        ).replayed
        row = session.get(Feedback, result.id)
        assert row.content is None and row.email is None
        audit = session.scalar(select(OperatorAuditOperation))
        assert audit.status == "succeeded"
        assert "private@example.test" not in str(audit.__dict__)
        assert session.scalar(select(FeedbackCooldown)).banned
    with factory() as session, pytest.raises(ApplicationError, match="feedback_banned"):
        OperationsService(session, feedback_secret="controlled-test").submit_feedback(
            owner_id=owner,
            command=FeedbackInput(operation_id=uuid4(), content="无法继续反馈"),
            client_ip="192.0.2.21",
            user_agent="controlled",
        )


def test_dictionary_is_versioned_and_revision_conflict_rolls_back_audit(event_read_client):
    owner = _user_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    command = DictionaryInput(
        operation_id=uuid4(),
        kind="entities",
        expected_version=0,
        content={"Acme": ["艾克米"]},
        reason="统一实体名称",
    )
    with factory() as session:
        service = OperationsService(session)
        first = service.save_dictionary(owner_id=owner, command=command)
        assert first.version == 1
        assert service.save_dictionary(owner_id=owner, command=command).id == first.id
        with pytest.raises(ApplicationError, match="operations_revision_conflict"):
            service.save_dictionary(
                owner_id=owner, command=command.model_copy(update={"operation_id": uuid4()})
            )
        current = service.list_dictionaries(owner_id=owner)
        assert len(current) == 1 and current[0].content == command.content
        audits, _ = service.list_audit(owner_id=owner)
        assert len(audits) == 1


def test_health_reports_actual_stale_heartbeat_not_a_configured_alive_process(event_read_client):
    owner = _user_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        record_process_heartbeat_in_transaction(
            session,
            owner_id=owner,
            role="worker",
            instance_id="controlled-worker",
            pid=12345,
            state="alive",
            now=now - timedelta(minutes=2),
            started_at=now - timedelta(hours=1),
        )
    with factory() as session:
        health = OperationsService(session, clock=lambda: now).get_health(owner_id=owner)
        assert len(health.heartbeats) == 1 and health.heartbeats[0].state == "stale"
        assert health.heartbeats[0].age_seconds == 120
        assert not health.maintenance_enabled and not health.backup_configured


def test_feedback_secret_missing_disables_submit_without_creating_rows(event_read_client):
    owner = _user_scope(event_read_client)
    with event_read_client.app.state.session_factory() as session:
        with pytest.raises(ApplicationError, match="feedback_disabled"):
            OperationsService(session).submit_feedback(
                owner_id=owner,
                command=FeedbackInput(operation_id=uuid4(), content="未配置反馈"),
                client_ip="192.0.2.20",
                user_agent="controlled",
            )
        assert session.scalar(select(Feedback)) is None


def test_operator_http_requires_independent_token_and_write_csrf(event_read_client):
    from pydantic import SecretStr

    client = event_read_client
    assert client.get("/api/operations/health").status_code == 403
    client.app.state.settings = client.app.state.settings.model_copy(
        update={
            "operator_token": SecretStr("controlled-operator"),
            "feedback_hmac_secret": SecretStr("controlled-feedback"),
        }
    )
    assert client.get("/api/operations/health").status_code == 401
    headers = {"X-HotKey-Operator-Token": "controlled-operator"}
    assert client.get("/api/operations/health", headers=headers).status_code == 200
    payload = {
        "operation_id": str(uuid4()),
        "kind": "glossary",
        "expected_version": 0,
        "content": {"model": ["模型"]},
        "reason": "统一用词",
    }
    assert (
        client.put("/api/operations/dictionaries", headers=headers, json=payload).status_code == 403
    )
    headers["X-HotKey-CSRF"] = event_read_client.cookies["hotkey_csrf"]
    assert (
        client.put("/api/operations/dictionaries", headers=headers, json=payload).status_code == 200
    )
    assert (
        client.post(
            "/api/feedback", json={"operation_id": str(uuid4()), "content": "提交意见"}
        ).status_code
        == 403
    )
    feedback = client.post(
        "/api/feedback",
        headers={"X-HotKey-CSRF": event_read_client.cookies["hotkey_csrf"]},
        json={"operation_id": str(uuid4()), "content": "提交意见"},
    )
    assert feedback.status_code == 201
    assert client.get("/api/operations/feedback").status_code == 401
    assert (
        client.get("/api/operations/feedback", headers=headers).json()["items"][0]["content"]
        == "提交意见"
    )
    second = client.post(
        "/api/feedback",
        headers={"X-HotKey-CSRF": event_read_client.cookies["hotkey_csrf"]},
        json={"operation_id": str(uuid4()), "content": "再次提交"},
    )
    assert second.status_code == 429 and 0 < int(second.headers["retry-after"]) <= 60


def test_operator_budget_cas_updates_real_ledger_and_replay_cannot_raise_twice(event_read_client):
    from jobs.schemas import BudgetPolicyInput
    from operations.schemas import BudgetUpdateInput

    owner = _user_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    command = BudgetUpdateInput(
        operation_id=uuid4(),
        expected_policy_version=0,
        reason="控制网络调用",
        policy=BudgetPolicyInput(
            budget_key="network.global",
            metric="network_request",
            scope_kind="global",
            window_anchor_at=datetime.now(UTC) - timedelta(minutes=1),
            window_seconds=86400,
            limit_units=100,
            enabled=True,
        ),
    )
    with factory() as session:
        service = OperationsService(session)
        first = service.update_budget(owner_id=owner, command=command)
        assert first.policy_version == 1
        changed = command.model_copy(
            update={
                "operation_id": uuid4(),
                "expected_policy_version": 1,
                "policy": command.policy.model_copy(update={"limit_units": 200}),
            }
        )
        second = service.update_budget(owner_id=owner, command=changed)
        assert second.policy_version == 2
        assert service.update_budget(owner_id=owner, command=changed).policy_version == 2
        with pytest.raises(ApplicationError, match="operations_revision_conflict"):
            service.update_budget(
                owner_id=owner, command=changed.model_copy(update={"operation_id": uuid4()})
            )
        budget = service.get_health(owner_id=owner).budgets[0]
        assert budget.policy_version == 2 and budget.remaining_units == 200


def test_action_audit_history_filters_owner_and_orders_actual_updates(event_read_client):
    from operations.services import (
        accept_audit_in_transaction,
        list_action_audits_in_transaction,
    )

    owner = _user_scope(event_read_client)
    factory = event_read_client.app.state.session_factory
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        identities = []
        for index in range(4):
            row, _ = accept_audit_in_transaction(
                session,
                owner_id=owner if index != 3 else uuid4(),
                operation_id=uuid4(),
                action="models.switch" if index != 2 else "dictionary.save",
                target_ref="models",
                reason="核对模型配置",
                payload={"index": index},
                now=now + timedelta(seconds=index),
            )
            identities.append(row.id)
        session.get(OperatorAuditOperation, identities[0]).updated_at = now + timedelta(seconds=10)
    with factory() as session, session.begin():
        before = list(session.scalars(select(OperatorAuditOperation)))
        views = list_action_audits_in_transaction(
            session, owner_id=owner, action="models.switch", limit=2
        )
        assert [row.id for row in views] == identities[:2]
        assert all(row.action == "models.switch" for row in views)
        assert len(list(session.scalars(select(OperatorAuditOperation)))) == len(before)
        with pytest.raises(ValueError):
            list_action_audits_in_transaction(
                session, owner_id=owner, action="models.switch", limit=101
            )
