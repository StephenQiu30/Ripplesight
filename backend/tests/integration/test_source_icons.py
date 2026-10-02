from __future__ import annotations

import io
import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from tests.integration.test_editorial_source_profiles import NOW, setup
from tests.integration.test_editorial_source_profiles import engine as engine

from connections.editorial_icon_services import (
    SourceIconService,
    enqueue_due_source_icons_in_transaction,
)
from core.config import Settings
from core.errors import ApplicationError
from jobs.execution import JobExecutionService
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    ComponentPolicyInput,
    CostClass,
    JobAcceptedMessage,
)
from jobs.services import ResourceBudgetService
from sources.icons_job import SourceIconJobExecutor
from sources.icons_reading import SourceIconReadingService
from sources.icons_schemas import SourceIconRefreshInput


class ControlledStorage:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.before_read = None
        self.fail_put = False

    def check_bucket(self):
        pass

    def put(self, name, body, mime_type):
        self.writes.append(name)
        self.objects[name] = body
        if self.fail_put:
            raise OSError("controlled uncertain object write")

    def get(self, name, *, max_bytes):
        if self.before_read:
            callback, self.before_read = self.before_read, None
            callback()
        assert len(self.objects[name]) <= max_bytes
        return self.objects[name]


def icon_setup(engine, *, media=True, enabled=True):
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as s:
        _, owner, profile, _ = setup(s)
        with s.begin():
            if media:
                s.execute(
                    text(
                        "UPDATE source_access_policies SET field_purposes=field_purposes || "
                        "CAST(:fields AS jsonb) "
                        "WHERE owner_id=:owner AND source_key=:key"
                    ),
                    dict(
                        owner=owner,
                        key=profile.source_key,
                        fields=json.dumps(
                            {
                                "url": "Independent source icon permission",
                                "source_icon": "Independent avatar purpose",
                            }
                        ),
                    ),
                )
                s.execute(
                    text(
                        "INSERT INTO evidence_retention_policies "
                        "(id,owner_id,source_policy_id,source_policy_version,data_class,"
                        "requested_days,effective_days,policy_version,created_at,updated_at) "
                        "SELECT :id,owner_id,id,policy_version,'media',30,30,1,:now,:now "
                        "FROM source_access_policies WHERE owner_id=:owner AND source_key=:key"
                    ),
                    dict(id=uuid4(), owner=owner, key=profile.source_key, now=NOW),
                )
            budgets = ResourceBudgetService(s, clock=lambda: NOW)
            budgets.save_component_policy_in_transaction(
                owner_id=owner,
                command=ComponentPolicyInput(
                    component_key="source.icons",
                    component_version="1",
                    cost_class=CostClass.ZERO_PRICE,
                    enabled_for_core=True,
                    terms_reference="Controlled software; no real source requests",
                    reviewed_at=NOW,
                ),
            )
            budgets.save_budget_policy_in_transaction(
                owner_id=owner,
                command=BudgetPolicyInput(
                    budget_key="controlled.icons",
                    metric=BudgetMetric.NETWORK_REQUEST,
                    scope_kind="global",
                    limit_units=100,
                    window_seconds=3600,
                    window_anchor_at=NOW,
                    enabled=True,
                ),
            )
            assert enqueue_due_source_icons_in_transaction(s, NOW, enabled=True) == 1
            s.flush()
            row = s.execute(
                text(
                    "SELECT o.id,o.event_type,o.payload FROM outbox_messages o JOIN jobs j "
                    "ON j.id=o.aggregate_id WHERE j.kind='source.icons'"
                )
            ).one()
        message = JobAcceptedMessage.model_validate(
            dict(**row.payload, message_id=row.id, event_type=row.event_type, schema_version=2)
        )
        lease = JobExecutionService(s, lease_seconds=30, clock=lambda: NOW).acquire(
            job_id=message.job_id, worker_id="controlled-icons"
        )
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=engine.url.render_as_string(hide_password=False),
        source_icons_enabled=enabled,
        source_icons_external_requests_enabled=enabled,
    )
    return sessions, owner, profile, message, lease, settings


def image():
    output = io.BytesIO()
    Image.new("RGB", (120, 60), "blue").save(output, format="PNG")
    return output.getvalue()


def executor(sessions, settings, storage, handler):
    return SourceIconJobExecutor(
        sessions,
        settings,
        clock=lambda: NOW,
        storage=storage,
        resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
    )


def test_icon_original_job_cache_evidence_avatar_two_sizes_read_no_source_fetch_and_revoke(engine):
    sessions, owner, p, message, lease, settings = icon_setup(engine)
    calls, storage = [], ControlledStorage()

    def handler(request):
        calls.append(request)
        if request.url.path == "/":
            return httpx.Response(
                200,
                text='<html><link rel="icon" href="/avatar.png"></html>',
                headers={"content-type": "text/html"},
            )
        return httpx.Response(200, content=image(), headers={"content-type": "image/png"})

    worker = executor(sessions, settings, storage, handler)
    result = worker.execute(message, lease)
    assert result.status == "succeeded" and len(calls) == 2 and len(storage.writes) == 2
    with sessions() as s:
        service = SourceIconService(s, clock=lambda: NOW)
        view = service.get(owner_id=owner, profile_id=p.id)
        assert view.status == "ready" and {v.width for v in view.variants} == {48, 96}
        reader = SourceIconReadingService(s, storage, clock=lambda: NOW)
        actual = reader.read(owner_id=owner, profile_id=p.id, mode="avatar-48")
        assert Image.open(io.BytesIO(actual.body)).size == (48, 48)
        assert actual.mime_type == "image/webp" and len(calls) == 2
        assert worker.execute(message, lease).status == "succeeded" and len(calls) == 2
        with s.begin():
            assert s.scalar(text("SELECT count(*) FROM evidence_resources")) == 1
            assert (
                s.scalar(
                    text("SELECT sum(jsonb_array_length(cleanup_targets)) FROM evidence_resources")
                )
                == 2
            )
            assert s.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 5
            assert (
                s.scalar(
                    text("SELECT requests_sent FROM jobs WHERE id=:id"), {"id": message.job_id}
                )
                == 5
            )

        def revoke():
            with sessions.begin() as tx:
                tx.execute(
                    text("UPDATE source_access_policies SET enabled=false WHERE source_key=:key"),
                    {"key": p.source_key},
                )

        storage.before_read = revoke
        with pytest.raises(ApplicationError, match="resource_not_found"):
            reader.read(owner_id=owner, profile_id=p.id, mode="avatar-48")
        assert service.get(owner_id=owner, profile_id=p.id).status == "blocked"
        assert len(calls) == 2


@pytest.mark.parametrize("media,enabled", [(False, True), (True, False)])
def test_icon_does_not_borrow_body_license_or_disabled_runtime(engine, media, enabled):
    sessions, owner, p, message, lease, settings = icon_setup(engine, media=media, enabled=enabled)
    calls, storage = [], ControlledStorage()
    result = executor(
        sessions,
        settings,
        storage,
        lambda request: calls.append(request) or httpx.Response(500),
    ).execute(message, lease)
    assert result.status == "partially_succeeded" and calls == [] and storage.writes == []
    with sessions() as s:
        assert (
            SourceIconService(s, clock=lambda: NOW).get(owner_id=owner, profile_id=p.id).status
            == "blocked"
        )


def test_icon_uncertain_http_is_persisted_unknown_zero_automatic_repeat_and_manual_cas(engine):
    sessions, owner, p, message, lease, settings = icon_setup(engine)
    calls, storage = [], ControlledStorage()

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("controlled no response", request=request)

    worker = executor(sessions, settings, storage, handler)
    assert worker.execute(message, lease).status == "partially_succeeded"
    assert worker.execute(message, lease).status == "partially_succeeded" and len(calls) == 1
    with sessions() as s:
        assert (
            SourceIconService(s, clock=lambda: NOW).get(owner_id=owner, profile_id=p.id).status
            == "unknown"
        )
        with s.begin():
            assert (
                enqueue_due_source_icons_in_transaction(s, NOW + timedelta(days=31), enabled=True)
                == 0
            )
            assert (
                s.scalar(
                    text(
                        "SELECT count(*) FROM resource_budget_reservations WHERE status='reserved'"
                    )
                )
                == 0
            )
        command = SourceIconRefreshInput(
            operation_id=uuid4(), expected_revision=p.revision, reason="Controlled manual proof"
        )
        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            SourceIconService(s, clock=lambda: NOW).refresh(
                owner_id=owner, profile_id=p.id, command=command
            )
        admitted = SourceIconService(s, clock=lambda: NOW).refresh(
            owner_id=owner,
            profile_id=p.id,
            command=command.model_copy(update={"action": "retry_unknown"}),
        )
        assert admitted.kind == "source.icons" and len(calls) == 1


def test_icon_uncertain_minio_write_remains_unknown_with_cleanup_tracked(engine):
    sessions, owner, p, message, lease, settings = icon_setup(engine)
    calls, storage = [], ControlledStorage()
    storage.fail_put = True

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(200, text='<html><link rel="icon" href="/avatar.png"></html>')
            if request.url.path == "/"
            else httpx.Response(200, content=image())
        )

    worker = executor(sessions, settings, storage, handler)
    assert worker.execute(message, lease).status == "partially_succeeded"
    assert worker.execute(message, lease).status == "partially_succeeded"
    assert len(calls) == 2 and len(storage.writes) == 1
    with sessions() as s:
        assert (
            SourceIconService(s, clock=lambda: NOW).get(owner_id=owner, profile_id=p.id).status
            == "unknown"
        )
        with s.begin():
            assert (
                s.scalar(
                    text("SELECT sum(jsonb_array_length(cleanup_targets)) FROM evidence_resources")
                )
                == 2
            )


def test_icon_process_crash_recovers_original_cap_no_network_repeat_under_new_epoch(engine):
    from publication.media_mirror_meter import MediaRequestMeter
    from sources.icons_schemas import SourceIconSeed

    sessions, owner, p, message, lease, settings = icon_setup(engine)
    with sessions.begin() as s:
        raw = s.scalar(
            text("SELECT scope->>'source_icon' FROM jobs WHERE id=:id"), {"id": message.job_id}
        )
        seed = SourceIconSeed.model_validate_json(raw)
        assert SourceIconService(s, clock=lambda: NOW).begin_in_transaction(
            seed=seed, job_id=message.job_id, operation_id=message.operation_id
        )
    meter = MediaRequestMeter(
        sessions,
        message,
        lease,
        clock=lambda: NOW,
        source_key=p.source_key,
        lease_seconds=30,
        guard=lambda s: None,
        component_key="source.icons",
        budget_job_ref=str(message.job_id),
        stage_prefix="source.icons",
    )
    assert meter.before(uuid4(), "http", 1)
    later = NOW + timedelta(seconds=31)
    with sessions() as s:
        next_lease = JobExecutionService(s, lease_seconds=30, clock=lambda: later).acquire(
            job_id=message.job_id, worker_id="new-icons-process"
        )
    calls = []
    result = SourceIconJobExecutor(
        sessions,
        settings,
        clock=lambda: later,
        storage=ControlledStorage(),
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200)),
    ).execute(message, next_lease)
    assert result.status == "partially_succeeded" and calls == []
    with sessions() as s:
        assert (
            SourceIconService(s, clock=lambda: later).get(owner_id=owner, profile_id=p.id).status
            == "unknown"
        )
        with s.begin():
            assert (
                s.scalar(
                    text(
                        "SELECT count(*) FROM resource_budget_reservations WHERE status='reserved'"
                    )
                )
                == 0
            )
            assert s.scalar(text("SELECT used_units FROM resource_budget_windows")) == 1
            assert (
                s.scalar(
                    text("SELECT requests_sent FROM jobs WHERE id=:id"), {"id": message.job_id}
                )
                == 1
            )
            assert s.scalar(text("SELECT outcome FROM resource_usage_attempts")) == "failed"


def test_icon_retention_stop_hides_ready_cache_and_no_get_provider_request(engine):
    sessions, owner, p, message, lease, settings = icon_setup(engine)
    storage = ControlledStorage()
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(200, text='<html><link rel="icon" href="/avatar.png"></html>')
            if request.url.path == "/"
            else httpx.Response(200, content=image())
        )

    assert (
        executor(sessions, settings, storage, handler).execute(message, lease).status == "succeeded"
    )
    with sessions.begin() as s:
        s.execute(
            text(
                "UPDATE evidence_retention_policies SET requested_days=1,effective_days=1,"
                "policy_version=2 WHERE data_class='media'"
            )
        )
    with sessions() as s:
        assert (
            SourceIconService(s, clock=lambda: NOW).get(owner_id=owner, profile_id=p.id).status
            == "blocked"
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            SourceIconReadingService(s, storage, clock=lambda: NOW).read_by_source_key(
                owner_id=owner, source_key=p.source_key, mode="avatar-96"
            )
    assert len(calls) == 2


def test_icon_configuration_changes_before_execution_make_zero_requests(engine):
    sessions, owner, p, message, lease, settings = icon_setup(engine)
    with sessions.begin() as s:
        s.execute(
            text("UPDATE editorial_source_profiles SET revision=revision+1 WHERE id=:id"),
            {"id": p.id},
        )
    calls, storage = [], ControlledStorage()
    result = executor(
        sessions, settings, storage, lambda request: calls.append(request) or httpx.Response(200)
    ).execute(message, lease)
    assert result.status == "partially_succeeded" and calls == [] and storage.writes == []
    with sessions() as s:
        assert (
            SourceIconService(s, clock=lambda: NOW).get(owner_id=owner, profile_id=p.id).status
            == "not_configured"
        )
