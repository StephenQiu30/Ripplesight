from uuid import uuid4

import pytest
from sqlalchemy import select
from tests.integration.test_editorial_execution import editorial_client as editorial_client
from tests.integration.test_identity_login import create_account, login, write_headers
from tests.integration.test_identity_login import identity_app as identity_app

from identity.models import IdentityUser
from notifications.email_subscription import (
    email_target_eligible_in_transaction,
    report_email_target_id,
)
from notifications.models import NotificationTarget

URL = "/api/notifications/email-subscription"


def test_user_subscribes_only_verified_binding_with_csrf_cas_and_owner_isolation(identity_app):
    app, client, _mail, _store = identity_app
    owner = create_account(app, "mail.owner", "owner@example.com")
    create_account(app, "mail.other", "other@example.com")
    assert client.get(URL).status_code == 401
    login(client, "mail.owner")
    first = client.get(URL)
    assert first.status_code == 200 and first.headers["cache-control"] == "private, no-store"
    assert first.json()["email"] == "owner@example.com" and first.json()["revision"] == 0
    command = {"operation_id": str(uuid4()), "expected_revision": 0, "enabled": True}
    assert client.put(URL, json=command).status_code == 403
    assert (
        client.put(
            URL, json={**command, "email": "other@example.com"}, headers=write_headers(client)
        ).status_code
        == 422
    )
    response = client.put(URL, json=command, headers=write_headers(client))
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] and not response.json()["delivery_available"]
    assert client.put(URL, json=command, headers=write_headers(client)).json() == response.json()
    conflict = {**command, "operation_id": str(uuid4())}
    assert client.put(URL, json=conflict, headers=write_headers(client)).status_code == 409
    client.cookies.clear()
    login(client, "mail.other")
    other = client.get(URL).json()
    assert other["email"] == "other@example.com" and not other["enabled"] and other["revision"] == 0
    with app.state.session_factory.begin() as session:
        target = session.scalar(select(NotificationTarget))
        assert target.owner_id == owner and target.recipients == ["owner@example.com"]
        assert target.id == report_email_target_id(owner) and target.subscriptions == ["report"]


def test_unbound_email_cannot_subscribe_and_changed_binding_invalidates_old_target(identity_app):
    app, client, _mail, _store = identity_app
    owner = create_account(app, "mail.change")
    login(client, "mail.change")
    command = {"operation_id": str(uuid4()), "expected_revision": 0, "enabled": True}
    missing = client.put(URL, json=command, headers=write_headers(client))
    assert missing.status_code == 422 and missing.json()["code"] == "notification_email_not_bound"
    with app.state.session_factory.begin() as session:
        session.get(IdentityUser, owner).email = "before@example.com"
    first = client.put(URL, json=command, headers=write_headers(client))
    assert first.status_code == 200
    with app.state.session_factory.begin() as session:
        target = session.get(NotificationTarget, report_email_target_id(owner))
        assert email_target_eligible_in_transaction(session, owner_id=owner, target=target)
        session.get(IdentityUser, owner).email = "after@example.com"
        session.flush()
        assert not email_target_eligible_in_transaction(session, owner_id=owner, target=target)
    assert client.get(URL).json()["enabled"] is False
    resubscribe = {"operation_id": str(uuid4()), "expected_revision": 1, "enabled": True}
    updated = client.put(URL, json=resubscribe, headers=write_headers(client))
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    with app.state.session_factory.begin() as session:
        target = session.get(NotificationTarget, report_email_target_id(owner))
        assert target.recipients == ["after@example.com"]
        assert email_target_eligible_in_transaction(session, owner_id=owner, target=target)
    disabled = client.put(
        URL,
        json={"operation_id": str(uuid4()), "expected_revision": 2, "enabled": False},
        headers=write_headers(client),
    )
    assert (
        disabled.status_code == 200
        and disabled.json()["revision"] == 3
        and not disabled.json()["enabled"]
    )


@pytest.mark.parametrize("changed", [None, "email", "topic", "disabled"])
def test_self_service_report_send_revalidates_email_topic_and_opt_out(editorial_client, changed):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text
    from tests.conftest import authenticated_headers
    from tests.integration.test_content_search import _seed_posts
    from tests.integration.test_notifications_pipeline import _lease
    from tests.unit.test_notification_smtp import FakeSmtp

    from jobs.execution import JobExecutionFailure
    from jobs.schemas import BudgetMetric, BudgetPolicyInput, BudgetScopeKind
    from jobs.services import ResourceBudgetService
    from notifications.executor import NotificationExecutor
    from notifications.models import NotificationDelivery
    from notifications.scan import NotificationScanExecutor
    from notifications.services import NotificationService
    from reports.services import ReportService

    owner, topic, _posts = _seed_posts(editorial_client, [("AI", "AI body")])
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        session.get(IdentityUser, owner).email = "reports@example.com"
    enabled = editorial_client.put(
        URL,
        json={"operation_id": str(uuid4()), "expected_revision": 0, "enabled": True},
        headers=authenticated_headers(editorial_client),
    )
    assert enabled.status_code == 200, enabled.text
    now = datetime.now(UTC)
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE monitor_topics SET notification_target_names=CAST(:names AS jsonb) "
                "WHERE id=:id"
            ),
            {"names": '["我的报告邮箱"]', "id": topic},
        )
        report = ReportService(session, clock=lambda: now).generate_daily_in_transaction(
            owner_id=owner,
            topic_id=topic,
            window_start=now - timedelta(days=1),
            window_end=now,
            cutoff_at=now,
        )
    with sessions() as session:
        ResourceBudgetService(session, clock=lambda: now).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="global.notification-test",
                metric=BudgetMetric.NETWORK_REQUEST,
                scope_kind=BudgetScopeKind.GLOBAL,
                limit_units=10,
                window_seconds=3600,
                window_anchor_at=now,
                enabled=True,
            ),
        )
    at = now + timedelta(minutes=5)
    settings = editorial_client.app.state.settings.model_copy(
        update={
            "notifications_enabled": True,
            "notification_smtp_enabled": True,
            "notification_smtp_host": "smtp.invalid",
            "notification_smtp_from_email": "hotkey@example.com",
        }
    )
    with sessions.begin() as session:
        assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 1
        assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 0
    scan, scan_lease = _lease(sessions, "notification.scan", at)
    NotificationScanExecutor(sessions, settings, clock=lambda: at).execute(scan, scan_lease)
    message, lease = _lease(sessions, "notification.send", at)
    with sessions.begin() as session:
        if changed == "email":
            session.get(IdentityUser, owner).email = "changed@example.com"
        elif changed == "topic":
            session.execute(
                text(
                    "UPDATE monitor_topics SET notification_target_names='[]'::jsonb WHERE id=:id"
                ),
                {"id": topic},
            )
        elif changed == "disabled":
            session.get(NotificationTarget, report_email_target_id(owner)).enabled = False
    smtp = FakeSmtp()
    executor = NotificationExecutor(
        sessions, settings, clock=lambda: at, smtp_factory=lambda *args, **kwargs: smtp
    )
    if changed:
        with pytest.raises(JobExecutionFailure):
            executor.execute(message, lease)
        assert not smtp.commands
    else:
        executor.execute(message, lease)
        executor.execute(message, lease)
        with sessions() as session:
            delivery = session.scalar(select(NotificationDelivery))
            assert delivery.report_id == report.id and delivery.status == "succeeded"
            assert (
                delivery.attempt_count == 1
                and delivery.provider_receipt["status"] == "smtp_accepted"
            )
