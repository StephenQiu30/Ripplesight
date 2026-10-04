"""Controlled PostgreSQL alert contracts; no source/model or notification send is invoked."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.conftest import authenticate_test_client, authenticated_headers
from tests.integration.test_editorial_source_profiles import NOW, setup
from tests.integration.test_editorial_topic_matches import _ingest, _topic
from tests.integration.test_editorial_topic_matches import engine as engine
from tests.integration.test_notifications_pipeline import _lease

from analysis.models import ContentAnnotation
from content.models import ContentObservation, ContentVersion
from content.version_inputs import save_version_inputs_in_transaction
from core.config import Settings
from core.errors import ApplicationError
from events.alert_reading import load_heat_alert_facts_in_transaction
from events.heat_models import EventAttentionSnapshot, EventAttentionSource
from events.heat_schemas import ATTENTION_FORMULA_VERSION
from events.models import Event
from evidence.models import SourceAccessPolicy
from jobs.models import Job
from main import create_app
from notifications.alert_models import AlertEvaluation
from notifications.alert_schemas import AlertRuleInput
from notifications.alert_services import AlertService, evaluate_alert_rules_in_transaction
from notifications.materials import load_notification_material_in_transaction
from notifications.models import NotificationDelivery
from notifications.scan import NotificationScanExecutor
from notifications.schemas import TargetInput
from notifications.services import NotificationService, NotificationTargetService


def _seed(session, *, sentiment=True, proof=True, cooldown=3600):
    service, owner, profile, _ = setup(session)
    topic = _topic(session, owner, profile.id)
    _ingest(session, service, owner, profile)
    with session.begin():
        version = session.scalar(select(ContentVersion))
        if sentiment:
            call = uuid4()
            session.execute(
                text("""INSERT INTO ai_calls
                (id,owner_id,purpose,provider,model,prompt_version,input_fingerprint,status,
                 input_tokens,cached_input_tokens,output_tokens,reasoning_output_tokens,duration_ms,
                 created_at) VALUES (:id,:owner,'analysis.annotate','controlled','controlled',
                 'alert-controlled',:fingerprint,'succeeded',0,0,0,0,0,:now)"""),
                {"id": call, "owner": owner, "fingerprint": b"a" * 32, "now": NOW},
            )
            session.add(
                ContentAnnotation(
                    id=uuid4(),
                    owner_id=owner,
                    content_id=version.content_id,
                    content_version_id=version.id,
                    topic_id=topic.id,
                    topic_rule_version=1,
                    prompt_version="alert-controlled",
                    relevant=True,
                    relevance_reason="controlled",
                    sentiment="negative",
                    summary="受控负面样本",
                    viewpoints=[],
                    ai_call_id=call,
                    status="annotated",
                    result_state="valid",
                    error_code=None,
                    diagnostic_history=[],
                    first_valid_at=NOW + timedelta(minutes=2),
                    created_at=NOW,
                    updated_at=NOW + timedelta(minutes=2),
                )
            )
        target = NotificationTargetService(session).add_in_transaction(
            owner_id=owner,
            target=TargetInput(
                name="controlled alert target",
                channel="feishu",
                enabled=True,
                subscriptions=("report", "alert"),
            ),
            now=NOW,
        )
        if proof:
            # Existing M5 receipt is controlled fixture evidence, not a real recipient acceptance.
            session.add(
                NotificationDelivery(
                    id=uuid4(),
                    owner_id=owner,
                    report_id=None,
                    report_version=1,
                    target_id=target.id,
                    subject_kind="selected",
                    subject_id=uuid4(),
                    dedupe_key="controlled-proof",
                    revision=1,
                    target_revision=1,
                    input_fingerprint=b"p" * 32,
                    frozen_payload={},
                    provider_receipt={"status": "accepted"},
                    status="succeeded",
                    attempt_count=1,
                    sent_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
    settings = Settings(notifications_enabled=True)
    alert = AlertService(session, settings, clock=lambda: NOW + timedelta(minutes=6))
    command = AlertRuleInput(
        operation_id=uuid4(),
        expected_revision=0,
        name="controlled alert",
        topic_id=topic.id,
        topic_rule_version=1,
        metric="negative_count",
        threshold=1,
        cooldown_seconds=cooldown,
        target_id=target.id,
        target_revision=1,
        enabled=False,
    )
    rule = alert.save(owner_id=owner, command=command)
    return owner, profile, topic, version, target, settings, command, rule


def _enable(session, owner, settings, command, rule):
    return AlertService(session, settings, clock=lambda: NOW + timedelta(minutes=6)).save(
        owner_id=owner,
        rule_id=rule.id,
        command=command.model_copy(
            update={"operation_id": uuid4(), "expected_revision": 1, "enabled": True}
        ),
    )


def _evaluate(session, owner, target, minutes):
    with session.begin():
        return evaluate_alert_rules_in_transaction(
            session,
            owner_id=owner,
            target_id=target.id,
            target_revision=1,
            scan_at=NOW + timedelta(minutes=minutes),
            now=NOW + timedelta(minutes=minutes),
        )


def test_original_five_minute_notification_job_triggers_once_and_replay_keeps_frozen_inputs(engine):
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        owner, _profile, _topic_view, _version, _target, settings, command, rule = _seed(session)
        _enable(session, owner, settings, command, rule)
        at = NOW + timedelta(minutes=10)
        with session.begin():
            assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 1
            assert NotificationService(session, settings).enqueue_due_in_transaction(now=at) == 0
        message, lease = _lease(sessions, "notification.scan", at)
        executor = NotificationScanExecutor(sessions, settings, clock=lambda: at)
        executor.execute(message, lease)
        executor.execute(message, lease)
        with session.begin():
            evaluation = session.scalar(select(AlertEvaluation))
            deliveries = tuple(
                session.scalars(
                    select(NotificationDelivery).where(NotificationDelivery.subject_kind == "alert")
                )
            )
            assert evaluation.status == "triggered" and evaluation.value == 1
            assert evaluation.window_end - evaluation.window_start == timedelta(hours=1)
            assert evaluation.input_manifest["time_basis"] == "first_received"
            assert len(deliveries) == 1 and deliveries[0].subject_id == evaluation.id
            assert deliveries[0].report_id is None
            assert (
                session.scalar(
                    select(text("count(*)")).select_from(Job).where(Job.kind == "notification.send")
                )
                == 1
            )
            material = load_notification_material_in_transaction(
                session,
                owner_id=owner,
                kind="alert",
                subject_id=evaluation.id,
                revision=2,
                locator={},
                now=at,
            )
            assert material and material.fingerprint == deliveries[0].input_fingerprint.hex()
            assert (
                load_notification_material_in_transaction(
                    session,
                    owner_id=uuid4(),
                    kind="alert",
                    subject_id=evaluation.id,
                    revision=2,
                    locator={},
                    now=at,
                )
                is None
            )


def test_persistent_cooldown_and_unknown_delivery_do_not_create_another_send(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, _, target, settings, command, rule = _seed(session, cooldown=600)
        _enable(session, owner, settings, command, rule)
        _evaluate(session, owner, target, 10)
        _evaluate(session, owner, target, 15)
        with session.begin():
            delivery = session.scalar(
                select(NotificationDelivery).where(NotificationDelivery.subject_kind == "alert")
            )
            delivery.status = "unknown"
        _evaluate(session, owner, target, 20)
        with session.begin():
            rows = tuple(
                session.scalars(select(AlertEvaluation).order_by(AlertEvaluation.window_end))
            )
            assert [r.status for r in rows] == ["triggered", "cooldown", "cooldown"]
            assert rows[-1].reason == "alert_delivery_unknown"
            assert (
                session.scalar(
                    text("SELECT count(*) FROM notification_deliveries WHERE subject_kind='alert'")
                )
                == 1
            )
        _evaluate(session, owner, target, 20)
        assert len(AlertService(session, settings).history(owner_id=owner, rule_id=rule.id)) == 3


def test_original_all_permission_stop_and_rule_change_reject_pending_material(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, profile, _, _, target, settings, command, rule = _seed(session)
        active = _enable(session, owner, settings, command, rule)
        _evaluate(session, owner, target, 10)
        with session.begin():
            evaluation = session.scalar(select(AlertEvaluation))
            policy = session.scalar(
                select(SourceAccessPolicy).where(
                    SourceAccessPolicy.source_key == profile.source_key
                )
            )
            policy.enabled = False
        with session.begin():
            assert (
                load_notification_material_in_transaction(
                    session,
                    owner_id=owner,
                    kind="alert",
                    subject_id=evaluation.id,
                    revision=2,
                    locator={},
                    now=NOW + timedelta(minutes=10),
                )
                is None
            )
        _evaluate(session, owner, target, 15)
        with session.begin():
            latest = session.scalar(
                select(AlertEvaluation).order_by(AlertEvaluation.window_end.desc())
            )
            assert latest.status == "unknown" and latest.value is None
        disabled = AlertService(session, settings, clock=lambda: NOW + timedelta(minutes=10)).save(
            owner_id=owner,
            rule_id=rule.id,
            command=command.model_copy(
                update={
                    "operation_id": uuid4(),
                    "expected_revision": active.revision,
                    "enabled": False,
                }
            ),
        )
        assert not disabled.enabled
        with session.begin():
            assert (
                load_notification_material_in_transaction(
                    session,
                    owner_id=owner,
                    kind="alert",
                    subject_id=evaluation.id,
                    revision=2,
                    locator={},
                    now=NOW + timedelta(minutes=10),
                )
                is None
            )


def test_default_closed_configuration_is_idempotent_and_missing_prerequisite_is_blocked(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, _, _, settings, command, rule = _seed(session, sentiment=False, proof=False)
        assert (
            not rule.enabled
            and rule.readiness == "blocked"
            and rule.reason == "alert_target_unverified"
        )
        again = AlertService(session, settings, clock=lambda: NOW + timedelta(minutes=6)).save(
            owner_id=owner, command=command
        )
        assert again.id == rule.id and again.revision == 1
        with pytest.raises(ApplicationError, match="idempotency_conflict"):
            AlertService(session, settings).save(
                owner_id=owner, command=command.model_copy(update={"name": "changed"})
            )
        with pytest.raises(ApplicationError) as caught:
            _enable(session, owner, settings, command, rule)
        assert caught.value.code == "alert_prerequisite_unavailable"
        assert AlertService(session, settings).list_rules(owner_id=uuid4()) == []
        with pytest.raises(ApplicationError) as caught:
            AlertService(session, settings).history(owner_id=uuid4(), rule_id=rule.id)
        assert caught.value.code == "resource_not_found"


def test_one_hour_m3_baseline_requires_same_formula_and_live_exact_inputs(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, profile, topic, version, _, _, _, _ = _seed(session)
        event_id, source_id = uuid4(), uuid4()
        end = NOW + timedelta(minutes=70)
        with session.begin():
            session.add(
                Event(
                    id=event_id,
                    owner_id=owner,
                    topic_id=topic.id,
                    revision=1,
                    title="controlled",
                    summary="controlled",
                    first_seen_at=NOW,
                    first_seen_basis="discovered",
                    status="active",
                    merged_into_id=None,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            session.add(
                EventAttentionSource(
                    id=source_id,
                    owner_id=owner,
                    source_key=profile.source_key,
                    selector_kind="source",
                    selector_ref=profile.source_key,
                    name="controlled",
                    mode="editorial",
                    group_key=None,
                    owner_entity_key=None,
                    tier="T1",
                    first_party=False,
                    scheduled=False,
                    interval_seconds=300,
                    enabled=True,
                    revision=1,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            session.flush()
            manifest = {
                "inputs": [
                    {
                        "source_id": str(source_id),
                        "source_revision": 1,
                        "version_id": str(version.id),
                    }
                ]
            }
            for when, heat in ((end - timedelta(hours=1), 10), (end, 20)):
                session.add(
                    EventAttentionSnapshot(
                        id=uuid4(),
                        owner_id=owner,
                        topic_id=topic.id,
                        event_id=event_id,
                        event_revision=1,
                        window_end=when,
                        formula_version=ATTENTION_FORMULA_VERSION,
                        input_fingerprint=bytes([heat]) * 32,
                        input_manifest=manifest,
                        result={
                            "eligible": True,
                            "heat": heat,
                            "roster": [{"participant_key": "source:controlled"}],
                        },
                        complete=True,
                        computed_at=end,
                    )
                )
        with session.begin():
            facts = load_heat_alert_facts_in_transaction(
                session, owner_id=owner, topic_id=topic.id, event_id=event_id, end=end, now=end
            )
            assert facts.value == 10 and len(facts.manifest["snapshot_ids"]) == 2
            baseline = session.scalar(
                select(EventAttentionSnapshot).where(
                    EventAttentionSnapshot.window_end == end - timedelta(hours=1)
                )
            )
            baseline.formula_version = "controlled-incompatible"
        with session.begin():
            facts = load_heat_alert_facts_in_transaction(
                session, owner_id=owner, topic_id=topic.id, event_id=event_id, end=end, now=end
            )
            assert facts.value is None and facts.reason == "alert_heat_baseline_missing"


def test_all_upstream_profile_permission_is_required_before_alert_delivery(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, version, target, settings, command, rule = _seed(session)
        service, _, other_profile, _ = setup(session, owner_id=owner)
        _ingest(session, service, owner, other_profile)
        with session.begin():
            own = session.scalar(
                select(ContentObservation).where(
                    ContentObservation.content_version_id == version.id
                )
            )
            other = session.scalar(
                select(ContentObservation).where(
                    ContentObservation.content_version_id != version.id
                )
            )
            save_version_inputs_in_transaction(
                session,
                owner_id=owner,
                content_version_id=version.id,
                observation_ids=(own.id, other.id),
            )
        _enable(session, owner, settings, command, rule)
        _evaluate(session, owner, target, 10)
        with session.begin():
            evaluation = session.scalar(select(AlertEvaluation))
            policy = session.scalar(
                select(SourceAccessPolicy).where(
                    SourceAccessPolicy.source_key == other_profile.source_key
                )
            )
            policy.enabled = False
        with session.begin():
            assert (
                load_notification_material_in_transaction(
                    session,
                    owner_id=owner,
                    kind="alert",
                    subject_id=evaluation.id,
                    revision=2,
                    locator={},
                    now=NOW + timedelta(minutes=10),
                )
                is None
            )


def test_real_alert_http_is_owner_scoped_no_store_and_default_disabled_without_side_effects(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, _, _, _, command, rule = _seed(session, sentiment=False, proof=False)
    with TestClient(
        create_app(
            Settings(environment="test", database_url=os.environ["HOTKEY_TEST_DATABASE_URL"])
        )
    ) as client:
        authenticate_test_client(client, owner_id=owner)
        with Session(engine) as session:
            before = tuple(
                session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("jobs", "alert_evaluations", "resource_usage_attempts")
            )
        response = client.get("/api/alerts")
        assert response.status_code == 200 and "no-store" in response.headers["cache-control"]
        assert response.json()[0]["enabled"] is False
        assert response.json()[0]["readiness"] == "blocked"
        targets = client.get("/api/alerts/targets")
        assert targets.status_code == 200
        assert set(targets.json()[0]) == {"id", "name", "revision", "eligible", "reason"}
        assert client.get(f"/api/alerts/{rule.id}/history").json() == []
        update = command.model_copy(update={"operation_id": uuid4(), "expected_revision": 1})
        assert (
            client.put(f"/api/alerts/{rule.id}", json=update.model_dump(mode="json")).status_code
            == 403
        )
        written = client.put(
            f"/api/alerts/{rule.id}",
            json=update.model_dump(mode="json"),
            headers=authenticated_headers(client),
        )
        assert written.status_code == 200 and written.json()["revision"] == 2
        with Session(engine) as session:
            after = tuple(
                session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in ("jobs", "alert_evaluations", "resource_usage_attempts")
            )
            assert before == after
        authenticate_test_client(client)
        assert client.get("/api/alerts").json() == []
        assert client.get(f"/api/alerts/{rule.id}/history").status_code == 404
        client.cookies.clear()
        assert client.get("/api/alerts").status_code == 401


def test_negative_count_uses_one_latest_fixed_version_per_original_identity(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, profile, topic, _version, target, settings, command, rule = _seed(session)
        from connections.editorial_services import EditorialSourceService

        service = EditorialSourceService(session, clock=lambda: NOW)
        _ingest(session, service, owner, profile, title="New model revision")
        with session.begin():
            original = session.scalar(select(ContentAnnotation))
            latest = session.scalar(
                select(ContentVersion).where(ContentVersion.id != original.content_version_id)
            )
            assert latest and latest.content_id == original.content_id
            session.add(
                ContentAnnotation(
                    id=uuid4(),
                    owner_id=owner,
                    content_id=original.content_id,
                    content_version_id=latest.id,
                    topic_id=topic.id,
                    topic_rule_version=1,
                    prompt_version="alert-controlled",
                    relevant=True,
                    relevance_reason="controlled revision",
                    sentiment="negative",
                    summary="受控修订样本",
                    viewpoints=[],
                    ai_call_id=original.ai_call_id,
                    status="annotated",
                    result_state="valid",
                    error_code=None,
                    diagnostic_history=[],
                    first_valid_at=NOW + timedelta(minutes=3),
                    created_at=NOW,
                    updated_at=NOW + timedelta(minutes=3),
                )
            )
        _enable(session, owner, settings, command, rule)
        _evaluate(session, owner, target, 10)
        with session.begin():
            evaluation = session.scalar(select(AlertEvaluation))
            assert evaluation.value == 1
            assert len(evaluation.input_manifest["inputs"]) == 1
            assert evaluation.input_manifest["inputs"][0]["version_id"] == str(latest.id)


@pytest.mark.parametrize("condition", ("revoked", "expired", "analysis_changed"))
def test_history_rechecks_original_all_without_rewriting_trigger_audit(engine, condition):
    with Session(engine, expire_on_commit=False) as session:
        owner, profile, _, _, target, settings, command, rule = _seed(session)
        _enable(session, owner, settings, command, rule)
        _evaluate(session, owner, target, 10)
        at = NOW + timedelta(minutes=10)
        with session.begin():
            if condition == "revoked":
                session.scalar(
                    select(SourceAccessPolicy).where(
                        SourceAccessPolicy.source_key == profile.source_key
                    )
                ).enabled = False
            elif condition == "analysis_changed":
                annotation = session.scalar(select(ContentAnnotation))
                annotation.relevant = False
                annotation.sentiment = None
            else:
                at = NOW + timedelta(days=31)
        history = AlertService(session, settings, clock=lambda: at).history(
            owner_id=owner, rule_id=rule.id
        )
        assert history[0].status == "withdrawn" and history[0].value is None
        assert history[0].reason == "alert_input_unavailable"
        with session.begin():
            original = session.scalar(select(AlertEvaluation))
            assert original.status == "triggered" and original.value == 1
