# ruff: noqa: F811
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.test_editorial_source_profiles import (
    NOW,
    begin,
    engine,  # noqa: F401
    material,
    setup,
)

from connections.editorial_models import EditorialSourceRun
from connections.editorial_schemas import ExternalEditorialInput
from connections.editorial_services import EditorialSourceService
from content.editorial_ingest import EditorialContentIngestService
from core.config import Settings
from core.errors import ApplicationError
from jobs.execution import JobExecutionService, MessageReference
from jobs.schemas import JobAcceptedMessage, JobStatus
from main import create_app
from sources.editorial_job import EditorialSourceJobExecutor

TOKEN = "controlled-external-ingress-token-32-characters"
SALT = SecretStr("controlled-external-ingress-private-salt-32")


def configured(session):
    _, owner, profile, command = setup(session, kind="external")
    service = EditorialSourceService(
        session,
        clock=lambda: NOW,
        external_tokens={profile.id: SecretStr(TOKEN)},
        ingress_hmac_secret=SALT,
    )
    return service, owner, profile, command


def input_for(profile, *materials):
    return ExternalEditorialInput(
        operation_id=uuid4(),
        expected_revision=profile.revision,
        configuration_version=profile.configuration_version,
        materials=materials,
    )


def second_profile(session, service, owner, first, command):
    create = command.model_copy(
        update={"operation_id": uuid4(), "expected_revision": 0, "enabled": False}
    )
    profile = service.save_profile(owner_id=owner, command=create)
    with session.begin():
        policy_id = uuid4()
        session.execute(
            text(
                "INSERT INTO source_access_policies "
                "(id,owner_id,source_key,capability,status,enabled,access_basis,terms_reference,"
                "component_name,component_version,component_license,processing_purpose,"
                "field_purposes,reviewed_at,policy_version,created_at,updated_at) "
                "SELECT :id,owner_id,:key,capability,status,enabled,access_basis,terms_reference,"
                "component_name,component_version,component_license,processing_purpose,"
                "field_purposes,reviewed_at,policy_version,created_at,updated_at "
                "FROM source_access_policies WHERE owner_id=:owner AND source_key=:first"
            ),
            {"id": policy_id, "key": profile.source_key, "owner": owner, "first": first.source_key},
        )
        session.execute(
            text(
                "INSERT INTO evidence_retention_policies "
                "(id,owner_id,source_policy_id,source_policy_version,data_class,requested_days,"
                "effective_days,policy_version,created_at,updated_at) "
                "VALUES (:id,:owner,:policy,1,'structured',30,30,1,:now,:now)"
            ),
            {"id": uuid4(), "owner": owner, "policy": policy_id, "now": NOW},
        )
    return service.save_profile(
        owner_id=owner,
        profile_id=profile.id,
        command=create.model_copy(
            update={"operation_id": uuid4(), "expected_revision": 1, "enabled": True}
        ),
    )


def test_external_partial_receipts_preserve_original_identity_and_duplicate_replay(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = configured(session)
        bad = {"url": "http://127.0.0.1/private", "title": "Rejected private URL"}
        command = input_for(profile, material(), material(), bad)
        receipt = service.accept_ingress(
            owner_id=owner, profile_id=profile.id, command=command, peer_ip="192.0.2.10"
        )
        assert [item.status for item in receipt.items] == ["pending", "duplicate", "rejected"]
        assert receipt.items[1].duplicate_of == 0
        assert begin(service, owner, profile, receipt.job, command.operation_id).prepared_page
        result = service.apply_page(owner_id=owner, run_id=receipt.run_id)
        assert result.status == "partial" and result.created == 1
        complete = service.get_ingress_receipt(
            owner_id=owner, profile_id=profile.id, run_id=receipt.run_id
        )
        assert [item.status for item in complete.items] == ["succeeded", "duplicate", "rejected"]
        assert complete.items[0].content_id == complete.items[1].content_id
        assert complete.items[0].content_version_id == complete.items[1].content_version_id
        assert (
            service.accept_ingress(
                owner_id=owner, profile_id=profile.id, command=command, peer_ip="192.0.2.11"
            )
            == complete
        )
        assert service.get_profile(owner_id=owner, profile_id=profile.id).last_ok_at is None
        with session.begin():
            run = session.get(EditorialSourceRun, receipt.run_id)
            assert "127.0.0.1" not in str(run.prepared_page)
            assert "body_text" not in str(run.prepared_page)
            assert session.scalar(text("SELECT count(*) FROM content_records")) == 1
            assert session.scalar(text("SELECT count(*) FROM evidence_resources")) == 1
        duplicate = service.accept_ingress(
            owner_id=owner,
            profile_id=profile.id,
            command=input_for(profile, material()),
            peer_ip="192.0.2.10",
        )
        assert service.apply_page(owner_id=owner, run_id=duplicate.run_id).created == 0
        assert (
            service.get_ingress_receipt(
                owner_id=owner, profile_id=profile.id, run_id=duplicate.run_id
            )
            .items[0]
            .status
            == "duplicate"
        )


def test_external_lease_failure_rolls_back_all_items_and_keeps_pending_receipts(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = configured(session)
        command = input_for(
            profile,
            material(),
            material().model_copy(
                update={
                    "url": "https://example.com/second",
                    "identity_key": "url:https://example.com/second",
                }
            ),
        )
        receipt = service.accept_ingress(
            owner_id=owner, profile_id=profile.id, command=command, peer_ip="192.0.2.10"
        )
        active = True

        def ingest(current_session, partition, value):
            nonlocal active
            result = EditorialContentIngestService(
                current_session, clock=lambda: NOW
            ).ingest_in_transaction(owner_id=partition, command=value)
            active = False
            return result

        with pytest.raises(ApplicationError, match="editorial_version_conflict"):
            service.apply_page(
                owner_id=owner,
                run_id=receipt.run_id,
                guard=lambda *_: active,
                sink=ingest,
            )
        session.rollback()
        assert all(
            item.status == "pending"
            for item in service.get_ingress_receipt(
                owner_id=owner, profile_id=profile.id, run_id=receipt.run_id
            ).items
        )
        with session.begin():
            assert session.scalar(text("SELECT count(*) FROM content_records")) == 0
            assert session.scalar(text("SELECT count(*) FROM evidence_resources")) == 0


def test_external_rate_uses_original_jobs_and_expires_at_exact_sixty_seconds(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = configured(session)
        original = input_for(profile, material())
        first = service.accept_ingress(
            owner_id=owner, profile_id=profile.id, command=original, peer_ip="192.0.2.10"
        )
        for _ in range(9):
            service.accept_ingress(
                owner_id=owner,
                profile_id=profile.id,
                command=input_for(profile, material()),
                peer_ip="192.0.2.10",
            )
        assert (
            service.accept_ingress(
                owner_id=owner, profile_id=profile.id, command=original, peer_ip="192.0.2.10"
            )
            == first
        )
        with pytest.raises(ApplicationError, match="external_source_rate_limited") as error:
            service.accept_ingress(
                owner_id=owner,
                profile_id=profile.id,
                command=input_for(profile, material()),
                peer_ip="192.0.2.10",
            )
        assert error.value.context == {"retry_after_seconds": 60}
        service._clock = lambda: NOW + timedelta(seconds=60)
        service.accept_ingress(
            owner_id=owner,
            profile_id=profile.id,
            command=input_for(profile, material()),
            peer_ip="192.0.2.10",
        )
        with session.begin():
            assert len(session.scalars(select(EditorialSourceRun)).all()) == 11
            scopes = session.scalars(
                text("SELECT scope FROM jobs WHERE kind='source.editorial.ingest'")
            )
            assert all(
                "192.0.2.10" not in str(scope) and TOKEN not in str(scope) for scope in scopes
            )


def test_external_parallel_peer_quota_is_shared_across_profiles_and_owner_bound(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, first, command = configured(session)
        second = second_profile(session, service, owner, first, command)
    tokens = {first.id: SecretStr(TOKEN), second.id: SecretStr(TOKEN)}
    factory = sessionmaker(engine, expire_on_commit=False)

    def admit(index):
        profile = first if index % 2 == 0 else second
        with factory() as current:
            source = EditorialSourceService(
                current, clock=lambda: NOW, external_tokens=tokens, ingress_hmac_secret=SALT
            )
            try:
                source.accept_ingress(
                    owner_id=owner,
                    profile_id=profile.id,
                    command=input_for(profile, material()),
                    peer_ip="192.0.2.10",
                )
                return "accepted"
            except ApplicationError as error:
                assert error.code == "external_source_rate_limited"
                return "limited"

    with ThreadPoolExecutor(max_workers=12) as executor:
        outcomes = list(executor.map(admit, range(12)))
    assert outcomes.count("accepted") == 10 and outcomes.count("limited") == 2
    with factory() as session:
        source = EditorialSourceService(
            session, clock=lambda: NOW, external_tokens=tokens, ingress_hmac_secret=SALT
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            source.get_ingress_receipt(owner_id=uuid4(), profile_id=first.id, run_id=uuid4())
        with session.begin():
            scopes = session.scalars(
                text("SELECT scope FROM jobs WHERE kind='source.editorial.ingest'")
            ).all()
            assert len(scopes) == 10 and len({scope["ingress_peer_hash"] for scope in scopes}) == 1
        other, another_owner, another_profile, _ = configured(session)
        assert (
            other.accept_ingress(
                owner_id=another_owner,
                profile_id=another_profile.id,
                command=input_for(another_profile, material()),
                peer_ip="192.0.2.10",
            ).job.owner_id
            == another_owner
        )


def test_external_http_receipts_authentication_ignore_spoofed_forwarding_and_zero_read_writes(
    engine,
):
    with Session(engine, expire_on_commit=False) as session:
        _, _, profile, _ = configured(session)
    settings = Settings(
        environment="test",
        database_url=engine.url.render_as_string(hide_password=False),
        log_level="WARNING",
        editorial_external_tokens={profile.id: SecretStr(TOKEN)},
        editorial_ingress_hmac_secret=SALT,
    )
    app = create_app(settings)
    path = f"/api/editorial-sources/{profile.id}/ingest"
    headers = {"X-HotKey-CSRF": "1", "X-HotKey-Source-Token": TOKEN}
    command = input_for(profile, material())
    with TestClient(app, client=("192.0.2.10", 6200)) as client:
        assert client.post(path, json=command.model_dump(mode="json")).status_code == 403
        assert (
            client.post(
                path, headers={"X-HotKey-CSRF": "1"}, json=command.model_dump(mode="json")
            ).status_code
            == 401
        )
        accepted = client.post(path, headers=headers, json=command.model_dump(mode="json"))
        assert accepted.status_code == 202 and accepted.headers["cache-control"] == "no-store"
        receipt = accepted.json()
        read_path = path + "/" + receipt["run_id"]
        assert client.get(read_path).status_code == 401
        at = datetime.now(UTC) + timedelta(seconds=1)
        with app.state.session_factory() as session:
            lease = JobExecutionService(session, lease_seconds=300, clock=lambda: at).acquire(
                job_id=UUID(receipt["job"]["id"]), worker_id="controlled-ingress"
            )
            row = session.execute(
                text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
                {"job": lease.job_id},
            ).one()
            message = JobAcceptedMessage.model_validate(
                {
                    **row.payload,
                    "message_id": row.id,
                    "event_type": row.event_type,
                    "schema_version": 2,
                }
            )
        completion = EditorialSourceJobExecutor(
            app.state.session_factory,
            settings.model_copy(update={"editorial_sources_enabled": True}),
            lease_seconds=300,
            clock=lambda: at,
        ).execute(message, lease)
        assert completion is not None and completion.status is JobStatus.SUCCEEDED
        with app.state.session_factory() as session:
            JobExecutionService(session, lease_seconds=300, clock=lambda: at).complete(
                lease,
                completion=completion,
                message=MessageReference(
                    message_id=message.message_id, topic="controlled-ingress", partition=0, offset=0
                ),
            )
        counts_sql = text(
            "SELECT (SELECT count(*) FROM content_records),"
            "(SELECT count(*) FROM content_versions),(SELECT count(*) FROM evidence_resources),"
            "(SELECT count(*) FROM jobs),(SELECT count(*) FROM outbox_messages),"
            "(SELECT count(*) FROM operations_audit_operations)"
        )
        with app.state.session_factory() as session:
            before_reads = session.execute(counts_sql).one()
        for _ in range(2):
            read = client.get(read_path, headers=headers)
            assert read.status_code == 200 and read.json()["items"][0]["status"] == "succeeded"
            assert read.json()["job"]["status"] == "succeeded"
            assert (
                "body_text" not in read.text
                and TOKEN not in read.text
                and "192.0.2.10" not in read.text
            )
        with app.state.session_factory() as session:
            assert session.execute(counts_sql).one() == before_reads
        for index in range(9):
            response = client.post(
                path,
                headers={**headers, "X-Forwarded-For": f"198.51.100.{index}"},
                json=input_for(profile, material()).model_dump(mode="json"),
            )
            assert response.status_code == 202
        limited = client.post(
            path,
            headers={**headers, "X-Forwarded-For": "203.0.113.5"},
            json=input_for(profile, material()).model_dump(mode="json"),
        )
        assert limited.status_code == 429 and 1 <= int(limited.headers["retry-after"]) <= 60
        with app.state.session_factory() as session, session.begin():
            assert session.scalar(text("SELECT count(*) FROM content_records")) == 1
            assert session.scalar(text("SELECT count(*) FROM evidence_resources")) == 1
            session.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE source_key=:key"),
                {"key": profile.source_key},
            )
        assert client.get(read_path, headers=headers).status_code == 403
