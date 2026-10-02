from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_codex_resets import (
    NOW,
    Client,
    authorized,
    post,
    review,
    setup,
    source_post,
)
from tests.integration.test_codex_resets import engine as engine

from ai.schemas import AiCallError, AiFailureCode
from ai.services import AiService
from monitors.codex_execution import CodexResetExecutor, list_due_codex_monitors_in_transaction
from monitors.codex_schemas import MonitorConfiguration
from monitors.codex_services import CodexResetService
from sources.contracts import SourceCapability, SourcePage, SourcePageState, SourceStopReason


def test_due_reads_existing_monitor_cadence_without_creating_jobs(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        service, owner, monitor = setup(session)
        with session.begin():
            due = list_due_codex_monitors_in_transaction(session, now=NOW)
        assert due[0].monitor_id == monitor and due[0].owner_id == owner
        assert due[0].interval_seconds == 300 and due[0].due_at == NOW
        m = service.get_monitor(owner_id=owner, monitor_id=monitor)
        service.configure(
            owner_id=owner, monitor_id=monitor, expected_revision=m.revision, enabled=False
        )
        with session.begin():
            assert not list_due_codex_monitors_in_transaction(session, now=NOW + timedelta(hours=1))


def test_executor_blocks_unavailable_source_and_cancellation_without_external_calls(
    engine: Engine,
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        _, owner, monitor = setup(session)
    executor = CodexResetExecutor(sessionmaker(engine), clock=lambda: NOW)
    blocked = executor.execute(owner_id=owner, monitor_id=monitor, configuration_version=1)
    assert blocked.status == "blocked" and not blocked.verified
    cancelled = executor.execute(
        owner_id=owner, monitor_id=monitor, configuration_version=1, cancelled=lambda: True
    )
    assert cancelled.status == "cancelled" and cancelled.collected is None


def test_executor_checks_job_guard_before_provider_factory(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        _, owner, monitor = setup(session)
    calls: list[object] = []

    def factory(*args: object) -> object:
        calls.append(args)
        raise AssertionError("old execution must not create providers")

    executor = CodexResetExecutor(
        sessionmaker(engine),
        source_factory=factory,
        execution_guard=lambda session: False,
        clock=lambda: NOW,
    )
    result = executor.execute(
        owner_id=owner, monitor_id=monitor, configuration_version=1, job_id=uuid4()
    )
    assert result.status == "blocked" and result.reason == "execution_not_current" and not calls


class CompleteSource:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty

    def fetch_page(self, request: object) -> SourcePage:
        return SourcePage(
            source_key="x",
            capability=SourceCapability.SEARCH,
            state=SourcePageState.EMPTY if self.empty else SourcePageState.COMPLETE,
            items=()
            if self.empty
            else (source_post("992").model_copy(update={"text": "Will reset"}),),
            next_page_token=None,
            watermark=None,
            stop_reason=SourceStopReason.SOURCE_EMPTY
            if self.empty
            else SourceStopReason.END_OF_RESULTS,
            observed_at=NOW,
        )


def configured_setup(engine: Engine) -> tuple[UUID, UUID]:
    with Session(engine, expire_on_commit=False) as session:
        _, owner, monitor = setup(
            session,
            configuration=MonitorConfiguration(
                connection_id=uuid4(), connection_version=1, author_external_id="12345"
            ),
        )
    return owner, monitor


def test_executor_empty_complete_source_verifies_without_model(engine: Engine) -> None:
    owner, monitor = configured_setup(engine)
    executor = CodexResetExecutor(
        sessionmaker(engine),
        source_factory=lambda *args: (CompleteSource(empty=True), None, authorized()),
        clock=lambda: NOW,
    )
    result = executor.execute(owner_id=owner, monitor_id=monitor, configuration_version=1)
    assert result.status == "succeeded" and result.verified and result.processed == 0


def test_executor_model_and_notification_intents_share_persistent_pipeline(engine: Engine) -> None:
    owner, monitor = configured_setup(engine)
    _enable_ai_budget(engine, owner)
    seen = []

    def sink(session: Session, owner_id: object, monitor_id: object, intents: object) -> int:
        assert session.in_transaction()
        seen.extend(intents)
        return len(intents)

    executor = CodexResetExecutor(
        sessionmaker(engine),
        source_factory=lambda *args: (CompleteSource(), None, authorized()),
        ai_factory=lambda session: AiService(session, Client(), clock=lambda: NOW),
        notification_sink=sink,
        clock=lambda: NOW,
    )
    result = executor.execute(owner_id=owner, monitor_id=monitor, configuration_version=1)
    assert result.status == "succeeded" and result.verified and result.processed == 1
    assert len(seen) == result.notifications_enqueued == 1
    with Session(engine) as session:
        snap = CodexResetService(session, clock=lambda: NOW).snapshot(
            owner_id=owner, monitor_id=monitor
        )
        assert snap.events[0].status == "announced" and snap.monitor.last_verified_at == NOW


def test_notification_admission_failure_rolls_back_event_projection(engine: Engine) -> None:
    owner, monitor = configured_setup(engine)
    _enable_ai_budget(engine, owner)

    def sink(*args: object) -> int:
        raise RuntimeError("controlled notification admission failure")

    executor = CodexResetExecutor(
        sessionmaker(engine),
        source_factory=lambda *args: (CompleteSource(), None, authorized()),
        ai_factory=lambda session: AiService(session, Client(), clock=lambda: NOW),
        notification_sink=sink,
        clock=lambda: NOW,
    )
    with pytest.raises(RuntimeError, match="notification admission failure"):
        executor.execute(owner_id=owner, monitor_id=monitor, configuration_version=1)
    with Session(engine) as session, session.begin():
        assert session.scalar(text("SELECT count(*) FROM codex_reset_events")) == 0
        assert session.scalar(text("SELECT count(*) FROM codex_reset_event_posts")) == 0


def test_executor_cancelled_model_keeps_event_and_watermark_unverified(engine: Engine) -> None:
    owner, monitor = configured_setup(engine)
    _enable_ai_budget(engine, owner)
    cancelled = False

    class CancelClient(Client):
        def complete(self, **kwargs: object) -> object:
            nonlocal cancelled
            value = super().complete(**kwargs)
            cancelled = True
            return value

    executor = CodexResetExecutor(
        sessionmaker(engine),
        source_factory=lambda *args: (CompleteSource(), None, authorized()),
        ai_factory=lambda session: AiService(session, CancelClient(), clock=lambda: NOW),
        clock=lambda: NOW,
    )
    result = executor.execute(
        owner_id=owner,
        monitor_id=monitor,
        configuration_version=1,
        cancelled=lambda: cancelled,
    )
    assert result.status == "cancelled" and not result.processed and not result.verified
    with Session(engine) as session:
        snap = CodexResetService(session, clock=lambda: NOW).snapshot(
            owner_id=owner, monitor_id=monitor
        )
        assert not snap.events and snap.monitor.pending_count == 1
        assert snap.monitor.last_verified_at is None


def test_unknown_model_failure_is_not_automatically_called_on_next_tick(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        service, owner, monitor = setup(session)
        service.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("993", "Will reset"),),
            expected_configuration_version=1,
        )
    _enable_ai_budget(engine, owner)
    calls = []

    class TimeoutClient(Client):
        def complete(self, **kwargs: object) -> object:
            calls.append(kwargs)
            raise AiCallError(AiFailureCode.TIMEOUT)

    for _ in range(2):
        with Session(engine, expire_on_commit=False) as session:
            service = CodexResetService(
                session,
                ai=AiService(session, TimeoutClient(), clock=lambda: NOW),
                clock=lambda: NOW,
            )
            service.process_pending(owner_id=owner, monitor_id=monitor)
    assert len(calls) == 1


def test_interrupted_claim_is_unknown_until_explicit_idempotent_manual_retry(
    engine: Engine,
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        service, owner, monitor = setup(session)
        service.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("994", "Will reset"),),
            expected_configuration_version=1,
        )
        prepared = service.prepare_next(owner_id=owner, monitor_id=monitor)
        assert prepared is not None and service.begin_recognition(prepared=prepared)
    _enable_ai_budget(engine, owner)
    with Session(engine, expire_on_commit=False) as session:
        service = CodexResetService(
            session, ai=AiService(session, Client(), clock=lambda: NOW), clock=lambda: NOW
        )
        assert service.process_pending(owner_id=owner, monitor_id=monitor) == {
            "processed": 0,
            "failed": 0,
            "notifications_enqueued": 0,
        }
        unknown = service.list_posts(owner_id=owner, monitor_id=monitor, filter_key="review")[0]
        assert unknown.failure_code == "recognition_interrupted" and unknown.processed_at is None
        operation = review(unknown.review_version)
        after = service.resolve_post(
            owner_id=owner, monitor_id=monitor, post_id=unknown.id, action="retry", review=operation
        )
        assert after.review_version == unknown.review_version + 1 and not after.needs_review
        assert (
            service.resolve_post(
                owner_id=owner,
                monitor_id=monitor,
                post_id=unknown.id,
                action="retry",
                review=operation,
            )
            == after
        )
        assert service.process_pending(owner_id=owner, monitor_id=monitor) == {
            "processed": 1,
            "failed": 0,
            "notifications_enqueued": 0,
        }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 1
        assert set(connection.scalars(text("SELECT status FROM codex_reset_recognitions"))) == {
            "unknown",
            "applied",
        }


def test_source_unknown_or_abandoned_request_requires_operator_review(engine: Engine) -> None:
    from sources.adapters.editorial_http import EditorialSourceError

    owner, monitor = configured_setup(engine)
    calls = []

    class UnknownSource:
        def fetch_page(self, request):
            calls.append(request)
            raise EditorialSourceError("upstream_unknown", unknown=True)

    executor = CodexResetExecutor(
        sessionmaker(engine),
        source_factory=lambda *args: (UnknownSource(), None, authorized()),
        clock=lambda: NOW,
    )
    assert (
        executor.execute(owner_id=owner, monitor_id=monitor, configuration_version=1).status
        == "partial"
    )
    assert (
        executor.execute(
            owner_id=owner, monitor_id=monitor, configuration_version=1, force=True
        ).status
        == "blocked"
    )
    assert len(calls) == 1
    with Session(engine) as session:
        service = CodexResetService(session, clock=lambda: NOW)
        gaps = service.list_gaps(owner_id=owner, monitor_id=monitor)
        assert gaps[0].failure_code == "source_unknown" and gaps[0].state == "held"
        with session.begin():
            assert not list_due_codex_monitors_in_transaction(session, now=NOW + timedelta(hours=1))


def test_codex_configuration_operations_are_audited_and_replayed(engine: Engine) -> None:
    from monitors.codex_schemas import CodexConfigurationInput

    with Session(engine) as session:
        owner = uuid4()
        service = CodexResetService(session, clock=lambda: NOW)
        command = CodexConfigurationInput(
            operation_id=uuid4(),
            expected_revision=0,
            reason="Controlled configuration",
            enabled=False,
            configuration=MonitorConfiguration(),
        )
        created = service.save_configuration(owner_id=owner, command=command)
        assert service.save_configuration(owner_id=owner, command=command) == created
        with session.begin():
            assert (
                session.scalar(
                    text(
                        "SELECT count(*) FROM operations_audit_operations WHERE owner_id=:"
                        "owner AND status='succeeded'"
                    ),
                    dict(owner=owner),
                )
                == 1
            )
        changed = service.save_configuration(
            owner_id=owner,
            command=command.model_copy(
                update={
                    "operation_id": uuid4(),
                    "expected_revision": created.revision,
                    "configuration": MonitorConfiguration(author_external_id="12345"),
                }
            ),
        )
        assert changed.revision == created.revision + 1
        assert service.save_configuration(owner_id=owner, command=command) == created


def _runtime_setup(engine):
    import json
    from datetime import UTC, datetime

    from tests.integration.test_editorial_source_profiles import budgets

    from jobs.schemas import BudgetMetric, BudgetPolicyInput
    from jobs.services import ResourceBudgetService

    at = datetime(2026, 10, 2, 2, tzinfo=UTC)
    owner, connection = uuid4(), uuid4()
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        with session.begin():
            session.execute(
                text(
                    "INSERT INTO source_connections (id,owner_id,source_key,status,cur"
                    "rent_version,created_at,updated_at) VALUES (:id,:owner,'x','activ"
                    "e',1,:now,:now)"
                ),
                dict(id=connection, owner=owner, now=at),
            )
            session.execute(
                text(
                    "INSERT INTO source_connection_versions (connection_id,owner_id,ve"
                    "rsion,auth_kind,secret_ref,config,created_by,created_at) VALUES ("
                    ":id,:owner,1,'server_credential','env:CONTROLLED_X_TOKEN',CAST(:c"
                    "onfig AS jsonb),:owner,:now)"
                ),
                dict(
                    id=connection,
                    owner=owner,
                    now=at,
                    config=json.dumps({"allowed_hosts": ["api.x.com"]}),
                ),
            )
            policy = uuid4()
            session.execute(
                text(
                    "INSERT INTO source_access_policies (id,owner_id,source_key,capabi"
                    "lity,status,enabled,access_basis,terms_reference,component_name,c"
                    "omponent_version,component_license,processing_purpose,field_purpo"
                    "ses,reviewed_at,policy_version,created_at,updated_at) VALUES (:id"
                    ",:owner,'x','search','approved',true,'official_api','https://exam"
                    "ple.com/terms','official-x','controlled','MIT','Controlled announ"
                    "cements',CAST(:fields AS jsonb),:now,1,:now,:now)"
                ),
                dict(
                    id=policy,
                    owner=owner,
                    now=at,
                    fields=json.dumps(
                        {k: "Controlled policy" for k in ("external_id", "body", "text_scope")}
                    ),
                ),
            )
            session.execute(
                text(
                    "INSERT INTO evidence_retention_policies (id,owner_id,source_polic"
                    "y_id,source_policy_version,data_class,requested_days,effective_da"
                    "ys,policy_version,created_at,updated_at) VALUES (:id,:owner,:poli"
                    "cy,1,'structured',30,30,1,:now,:now)"
                ),
                dict(id=uuid4(), owner=owner, policy=policy, now=at),
            )
        budgets(session, owner)
        ResourceBudgetService(session, clock=lambda: at).save_budget_policy(
            owner_id=owner,
            command=BudgetPolicyInput(
                budget_key="controlled.xspend",
                metric=BudgetMetric.X_API_USD_MICROS,
                scope_kind="global",
                limit_units=1000000,
                window_seconds=3600,
                window_anchor_at=at - timedelta(minutes=1),
                enabled=True,
            ),
        )
        service = CodexResetService(session, clock=lambda: at)
        view = service.create_monitor(
            owner_id=owner,
            configuration=MonitorConfiguration(
                author_external_id="12345", connection_id=connection, connection_version=1
            ),
        )
        view = service.configure(
            owner_id=owner, monitor_id=view.id, expected_revision=view.revision, enabled=True
        )
        from monitors.codex_schemas import CodexTickInput

        job = service.enqueue_tick(
            owner_id=owner,
            monitor_id=view.id,
            command=CodexTickInput(
                operation_id=uuid4(),
                expected_revision=view.revision,
                reason="Controlled runtime replay",
            ),
        )
        from jobs.execution import JobExecutionService
        from jobs.schemas import JobAcceptedMessage

        with session.begin():
            outbox = session.execute(
                text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
                dict(job=job.id),
            ).one()
        message = JobAcceptedMessage.model_validate(
            dict(
                **outbox.payload,
                message_id=outbox.id,
                event_type=outbox.event_type,
                schema_version=2,
            )
        )
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: at).acquire(
            job_id=job.id, worker_id="controlled-codex"
        )
    return sessions, owner, view, message, lease, at


def test_official_codex_runtime_uses_real_job_ledger_and_preserves_paid_pause(
    engine: Engine,
) -> None:
    import os

    import httpx

    from core.config import Settings
    from jobs.schemas import JobStatus
    from monitors.codex_job import CodexResetJobExecutor

    sessions, owner, view, message, lease, at = _runtime_setup(engine)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "api.x.com" and request.url.params["start_time"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "992",
                        "author_id": "12345",
                        "text": "Will reset",
                        "created_at": (at - timedelta(hours=1)).isoformat(),
                    }
                ],
                "includes": {"users": [{"id": "12345", "username": "thsottiaux", "name": "Tibo"}]},
            },
        )

    settings = Settings(
        _env_file=None,
        database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
        codex_resets_enabled=True,
        editorial_x_authorized=True,
        editorial_x_token="controlled",
        editorial_x_post_unit_usd_micros=1000,
        ai_enabled=False,
    )
    result = CodexResetJobExecutor(
        sessions, settings, clock=lambda: at, transport=httpx.MockTransport(handler)
    ).execute(message, lease)
    assert result.status is JobStatus.PARTIALLY_SUCCEEDED and len(calls) == 1
    with sessions() as session:
        snap = CodexResetService(session, clock=lambda: at).snapshot(
            owner_id=owner, monitor_id=view.id
        )
        assert (
            snap.monitor.pending_count == 1
            and not snap.events
            and snap.monitor.last_verified_at is None
        )
        with session.begin():
            assert (
                session.scalar(
                    text("SELECT count(*) FROM ai_calls WHERE owner_id=:owner"), dict(owner=owner)
                )
                == 0
            )
            assert (
                session.scalar(
                    text("SELECT requests_sent FROM jobs WHERE id=:id"), dict(id=message.job_id)
                )
                == 1
            )
            assert (
                session.scalar(
                    text(
                        "SELECT used_units FROM resource_budget_windows w JOIN resource_bu"
                        "dget_policies p ON p.id=w.budget_policy_id WHERE w.owner_id=:owne"
                        "r AND p.metric='x_api_usd_micros'"
                    ),
                    dict(owner=owner),
                )
                == 1000
            )


def test_official_codex_runtime_unknown_charges_cap_and_disables_next_due(engine: Engine) -> None:
    import os

    import httpx

    from core.config import Settings
    from monitors.codex_job import CodexResetJobExecutor
    from monitors.codex_schedule import enqueue_due_codex_monitors_in_transaction

    sessions, owner, _view, message, lease, at = _runtime_setup(engine)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("controlled interrupted X response")

    settings = Settings(
        _env_file=None,
        database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
        codex_resets_enabled=True,
        editorial_x_authorized=True,
        editorial_x_token="controlled",
        editorial_x_post_unit_usd_micros=1000,
        ai_enabled=False,
    )
    executor = CodexResetJobExecutor(
        sessions, settings, clock=lambda: at, transport=httpx.MockTransport(handler)
    )
    executor.execute(message, lease)
    executor.execute(message, lease)
    assert len(calls) == 1
    with sessions.begin() as session:
        assert (
            enqueue_due_codex_monitors_in_transaction(
                session, at + timedelta(hours=1), enabled=True
            )
            == 0
        )
        assert (
            session.scalar(
                text(
                    "SELECT used_units FROM resource_budget_windows w JOIN resource_bu"
                    "dget_policies p ON p.id=w.budget_policy_id WHERE w.owner_id=:owne"
                    "r AND p.metric='x_api_usd_micros'"
                ),
                dict(owner=owner),
            )
            == 100000
        )


def test_codex_job_keeps_frozen_monitor_revision_after_pause_and_resume(engine: Engine) -> None:
    import os

    import httpx

    from core.config import Settings
    from jobs.execution import JobExecutionFailure
    from monitors.codex_job import CodexResetJobExecutor

    sessions, owner, view, message, lease, at = _runtime_setup(engine)
    with sessions() as session:
        service = CodexResetService(session, clock=lambda: at)
        paused = service.configure(
            owner_id=owner, monitor_id=view.id, expected_revision=view.revision, enabled=False
        )
        service.configure(
            owner_id=owner, monitor_id=view.id, expected_revision=paused.revision, enabled=True
        )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": []})

    settings = Settings(
        _env_file=None,
        database_url=os.environ["HOTKEY_TEST_DATABASE_URL"],
        codex_resets_enabled=True,
        editorial_x_authorized=True,
        editorial_x_token="controlled",
        editorial_x_post_unit_usd_micros=1000,
    )
    with pytest.raises(JobExecutionFailure, match="codex_job_mismatch"):
        CodexResetJobExecutor(
            sessions, settings, clock=lambda: at, transport=httpx.MockTransport(handler)
        ).execute(message, lease)
    assert calls == []


def test_retained_notification_admission_replays_without_new_model_recognition(engine: Engine):
    from tests.integration.test_codex_resets import apply

    with Session(engine, expire_on_commit=False) as session:
        service, owner, monitor = setup(session)
        applied = apply(service, owner, monitor, post("910", "Will reset"), "announce")
    calls = []

    def sink(session, partition, ident, intents):
        assert session.in_transaction()
        assert partition == owner and ident == monitor
        assert intents == applied.notifications
        stored = session.scalar(
            text("SELECT status FROM codex_reset_recognitions WHERE monitor_id=:monitor"),
            dict(monitor=monitor),
        )
        assert stored == "applied"
        calls.append(intents)
        return 1

    executor = CodexResetExecutor(sessionmaker(engine), clock=lambda: NOW, notification_sink=sink)
    result = executor.execute(owner_id=owner, monitor_id=monitor, configuration_version=1)
    assert result.processed == 0
    assert result.notifications_enqueued == 1
    assert len(calls) == 1


def test_codex_operational_health_is_metadata_only_recent_review_and_stuck_pending(engine):
    from monitors.codex_models import CodexResetPost
    from monitors.codex_services import read_codex_operational_health_in_transaction

    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            missing = read_codex_operational_health_in_transaction(
                session, owner_id=uuid4(), now=NOW
            )
            assert not missing.configured and not missing.enabled
        service, owner, monitor = setup(session)
        service.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            expected_configuration_version=1,
            posts=(post("501", "Controlled recent review"), post("502", "Controlled pending")),
        )
        with session.begin():
            rows = list(session.scalars(select(CodexResetPost)))
            for row in rows:
                row.collected_at = NOW - timedelta(hours=50)
            rows[0].needs_review = True
            rows[0].processed_at = NOW - timedelta(hours=1)
            session.flush()
            health = read_codex_operational_health_in_transaction(session, owner_id=owner, now=NOW)
            assert health.enabled and health.held_unreviewed_count == 1
            assert health.stuck_oldest_collected_at == NOW - timedelta(hours=50)
            rows[0].processed_at = NOW - timedelta(hours=49)
            session.flush()
            assert (
                read_codex_operational_health_in_transaction(
                    session, owner_id=owner, now=NOW
                ).held_unreviewed_count
                == 0
            )
