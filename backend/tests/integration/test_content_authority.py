"""Real P/J/V detail reads: no business transaction may bridge journal I/O."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from tests.integration.test_content_records import (
    _command,
    _seed_context,
    _user_scope,
)
from tests.integration.test_content_records import (
    content_client as content_client,
)
from tests.integration.test_independent_journal import command

from analysis.models import ContentAnnotation
from analysis.prompts import ANALYSIS_PROMPT_VERSION
from content.analysis_inputs import freeze_analysis_observation_inputs_in_transaction
from content.services import ContentService
from core.errors import ApplicationError, AuthorityUnavailableError
from evidence.journal import RestrictionJournal


@pytest.fixture
def detail_context(content_client, runtime_journal):
    owner = _user_scope(content_client)
    now = datetime.now(UTC)
    connection, policy, retention, job, _ = _seed_context(content_client, owner, now=now)
    factory = content_client.app.state.session_factory
    with factory() as session:
        record = ContentService(session, clock=lambda: now).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=job,
                operation_id=uuid4(),
                observed_at=now,
                extra_fields={
                    "body": "original source text",
                    "text_scope": "full",
                    "text_origin": "source",
                    "title": "Original",
                },
            ),
        )
    return content_client, factory, owner, record, now, policy, runtime_journal


def _deny(context, *, observation=None):
    _, _, owner, record, _, _, journal = context
    journal.writer.append(
        command(
            owner_id=owner,
            resource_type="content_observation",
            resource_id=observation or record.latest_observation.id,
        )
    )


def _read(context):
    _, factory, owner, record, _, _, _ = context
    with factory() as session:
        return ContentService(session).get_content(owner_id=owner, content_id=record.id)


def _persist_extra(context, *, external="post-001", fields=None, offset=1):
    _, factory, owner, record, now, policy, _ = context
    with factory() as session:
        connection = session.scalar(
            text("SELECT id FROM source_connections WHERE owner_id=:owner"), {"owner": owner}
        )
        retention = session.scalar(
            text("SELECT id FROM evidence_retention_policies WHERE source_policy_id=:policy"),
            {"policy": policy},
        )
        job = session.scalar(
            text("SELECT job_id FROM content_observations WHERE id=:id"),
            {"id": record.latest_observation.id},
        )
        session.commit()
        observed = now + timedelta(microseconds=offset)
        return ContentService(session, clock=lambda: observed).persist_post(
            owner_id=owner,
            command=_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=job,
                operation_id=uuid4(),
                observed_at=observed,
                external_id=external,
                extra_fields=fields or {},
            ),
        )


def test_metadata_only_metrics_root_is_checked_by_journal(detail_context):
    metrics = _persist_extra(detail_context)
    assert metrics.latest_observation.content_version is None
    assert _read(detail_context).latest_observation.id == metrics.latest_observation.id
    _deny(detail_context, observation=metrics.latest_observation.id)
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)


def test_source_33_beyond_display_limit_is_still_a_journal_dependency(detail_context):
    for index in range(32):
        _persist_extra(
            detail_context,
            offset=index + 1,
            fields={
                "body": "original source text",
                "text_scope": "full",
                "text_origin": "source",
                "title": "Original",
            },
        )
    detail = _read(detail_context)
    assert detail.readable_sources_total == 33 and len(detail.readable_sources) == 32
    assert detail.readable_sources_truncated
    _, _, _, original, _, _, _ = detail_context
    assert original.latest_observation.id not in {
        item.observation_id for item in detail.readable_sources
    }
    _deny(detail_context)
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)


def test_added_edge_after_journal_is_rechecked_with_its_new_root(detail_context, monkeypatch):
    _, factory, owner, record, _, _, _ = detail_context
    dependency = _persist_extra(
        detail_context,
        external="new-input",
        fields={"body": "independent input", "text_scope": "full", "text_origin": "source"},
    )
    actual = RestrictionJournal.denied_resources
    calls = []

    def read(reader, **kwargs):
        calls.append(kwargs["resources"])
        result = actual(reader, **kwargs)
        if len(calls) == 1:
            _deny(detail_context, observation=dependency.latest_observation.id)
            with factory.begin() as session:
                session.execute(
                    text(
                        "UPDATE content_observations SET input_basis='observations_v1' WHERE id=:id"
                    ),
                    {"id": record.latest_observation.id},
                )
                session.execute(
                    text(
                        "INSERT INTO content_observation_inputs "
                        "(owner_id,output_observation_id,input_observation_id) "
                        "VALUES (:owner,:output,:input)"
                    ),
                    {
                        "owner": owner,
                        "output": record.latest_observation.id,
                        "input": dependency.latest_observation.id,
                    },
                )
        return result

    monkeypatch.setattr(RestrictionJournal, "denied_resources", read)
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)
    assert len(calls) == 2
    assert ("content_observation", dependency.latest_observation.id) not in calls[0]
    assert ("content_observation", dependency.latest_observation.id) in calls[1]


@pytest.mark.parametrize("denial", ["annotation", "input"])
def test_annotation_key_and_original_manifest_member_are_journal_dependencies(
    detail_context, denial
):
    _, factory, owner, record, now, _, journal = detail_context
    dependency = _persist_extra(
        detail_context,
        external="annotation-input",
        fields={"body": "analysis input", "text_scope": "full", "text_origin": "source"},
    )
    from tests.integration.test_analysis_observation_inputs import topic

    annotation_id = uuid4()
    with factory.begin() as session:
        topic_id = topic(session, owner)
        manifest = freeze_analysis_observation_inputs_in_transaction(
            session,
            owner_id=owner,
            post_observations={
                record.latest_observation.content_version.id: record.latest_observation.id,
                dependency.latest_observation.content_version.id: dependency.latest_observation.id,
            },
            comment_observations={},
            now=now + timedelta(seconds=1),
        )
        session.add(
            ContentAnnotation(
                id=annotation_id,
                owner_id=owner,
                content_id=record.id,
                content_version_id=record.latest_observation.content_version.id,
                topic_id=topic_id,
                topic_rule_version=1,
                prompt_version=ANALYSIS_PROMPT_VERSION,
                input_manifest=manifest.model_dump(mode="json"),
                input_signature=manifest.signature,
                relevant=None,
                relevance_reason=None,
                sentiment=None,
                summary=None,
                ai_call_id=None,
                status="unanalyzed",
                result_state="pending",
                first_valid_at=None,
                created_at=now,
                updated_at=now,
            )
        )
    assert [item.id for item in _read(detail_context).annotations] == [annotation_id]
    journal.writer.append(
        command(
            owner_id=owner,
            resource_type="content_annotation" if denial == "annotation" else "content_observation",
            resource_id=annotation_id
            if denial == "annotation"
            else dependency.latest_observation.id,
        )
    )
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)


def test_internal_relation_target_has_its_own_journal_dependency(detail_context):
    target = _persist_extra(
        detail_context,
        external="quote-target",
        fields={"body": "quoted", "text_scope": "full", "text_origin": "source"},
    )
    _persist_extra(
        detail_context,
        fields={
            "body": "quote",
            "text_scope": "full",
            "text_origin": "source",
            "quote_target_external_id": "quote-target",
        },
    )
    detail = _read(detail_context)
    assert detail.latest_observation.content_version.relations[0].target_content_id == target.id
    _deny(detail_context, observation=target.latest_observation.id)
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)


def test_relation_resolution_uses_exact_observation_source_not_canonical_first(detail_context):
    _, factory, _, record, _, _, _ = detail_context
    target = _persist_extra(
        detail_context,
        external="actual-target",
        fields={"body": "target", "text_scope": "full", "text_origin": "source"},
    )
    _persist_extra(
        detail_context,
        fields={
            "body": "quote",
            "text_scope": "full",
            "text_origin": "source",
            "quote_target_external_id": "actual-target",
        },
    )
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE content_records SET source_key='canonical_first' WHERE id IN (:id,:target)"
            ),
            {"id": record.id, "target": target.id},
        )
    detail = _read(detail_context)
    assert detail.source_key == "x"
    assert detail.latest_observation.content_version.relations[0].target_content_id == target.id


def test_inactive_session_discards_held_orm_before_a_new_snapshot(detail_context):
    from content.models import ContentObservation

    _, factory, owner, record, _, _, _ = detail_context
    with factory() as session:
        held = session.get(ContentObservation, record.latest_observation.id)
        session.commit()
        with factory.begin() as other:
            other.execute(
                text("UPDATE content_observations SET like_count=42 WHERE id=:id"), {"id": held.id}
            )
        detail = ContentService(session).get_content(owner_id=owner, content_id=record.id)
        assert detail.latest_observation.metrics.like_count == 42


@pytest.mark.parametrize("mutation", ["version", "metrics"])
def test_v_rebuilds_version_and_dto_semantics(detail_context, monkeypatch, mutation):
    _, factory, _, record, _, _, _ = detail_context
    actual = RestrictionJournal.denied_resources
    calls = []

    def read(reader, **kwargs):
        calls.append(1)
        result = actual(reader, **kwargs)
        if len(calls) == 1:
            with factory.begin() as session:
                if mutation == "version":
                    session.execute(
                        text("UPDATE content_versions SET title='Changed' WHERE id=:id"),
                        {"id": record.latest_observation.content_version.id},
                    )
                else:
                    session.execute(
                        text("UPDATE content_observations SET like_count=7 WHERE id=:id"),
                        {"id": record.latest_observation.id},
                    )
        return result

    monkeypatch.setattr(RestrictionJournal, "denied_resources", read)
    detail = _read(detail_context)
    assert len(calls) == 2
    assert (
        detail.latest_observation.content_version.title == "Changed"
        if mutation == "version"
        else detail.latest_observation.metrics.like_count == 7
    )


def test_adopted_hotlist_mapping_is_unknown_without_original_material_proof(detail_context):
    from tests.integration.test_analysis_observation_inputs import topic

    _, factory, owner, record, now, _, _ = detail_context
    assert _read(detail_context).analysis_topics == []
    with factory.begin() as session:
        topic_id = topic(session, owner)
        job, operation = session.execute(
            text(
                "SELECT j.id,j.operation_id FROM jobs j JOIN "
                "content_observations o ON o.job_id=j.id WHERE o.id=:id"
            ),
            {"id": record.latest_observation.id},
        ).one()
        snapshot = uuid4()
        session.execute(
            text(
                "INSERT INTO collection_due_windows "
                "(id,owner_id,schedule_key,source_key,capability,due_at,window_start,window_end,"
                "admission_state,operation_id,job_id,recorded_at) VALUES "
                "(:id,:owner,:schedule,'x','search',:now,:start,:now,'accepted',:op,:job,:now)"
            ),
            {
                "id": uuid4(),
                "owner": owner,
                "schedule": uuid4(),
                "now": now,
                "start": now - timedelta(hours=1),
                "op": operation,
                "job": job,
            },
        )
        session.execute(
            text(
                "INSERT INTO hotlist_snapshots "
                "(id,owner_id,source_key,job_id,operation_id,observed_at,entry_count) "
                "VALUES (:id,:owner,'x',:job,:op,:now,1)"
            ),
            {"id": snapshot, "owner": owner, "job": job, "op": operation, "now": now},
        )
        session.execute(
            text(
                "INSERT INTO hotlist_entries "
                "(snapshot_id,rank,owner_id,title,url,content_id,"
                "matched_topic_names,matched_topic_ids) "
                "VALUES (:id,1,:owner,'hotlist','https://example.invalid',:content,'[]'::jsonb,"
                "CAST(:topics AS jsonb))"
            ),
            {
                "id": snapshot,
                "owner": owner,
                "content": record.id,
                "topics": '["' + str(topic_id) + '"]',
            },
        )
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)


def test_group_job_discovery_returns_exact_member_configuration(content_client):
    import httpx
    from tests.integration.test_editorial_group_runtime import (
        admitted_group,
        controlled_settings,
        group_setup,
        official_answer,
    )

    from sources.editorial_group_job import EditorialXGroupJobExecutor

    engine = content_client.app.state.session_factory.kw["bind"]
    sessions, owner, profiles, now = group_setup(engine)
    message, lease = admitted_group(sessions, now)
    result = EditorialXGroupJobExecutor(
        sessions,
        controlled_settings(engine),
        zero_supplier_fee_only=False,
        clock=lambda: now,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=official_answer(now))
        ),
    ).execute(message, lease)
    assert result.status == "succeeded"
    with sessions() as session:
        records = session.execute(text("SELECT id,source_key FROM content_records")).all()
        session.commit()
        for identifier, source in records:
            detail = ContentService(session, clock=lambda: now).get_content(
                owner_id=owner, content_id=identifier
            )
            profile = next(item for item in profiles if item.source_key == source)
            assert {item.configuration_ref for item in detail.discoveries} == {
                f"editorial-source:{profile.id}"
            }


def test_relation_old_source_witness_is_not_replaced_by_latest_alias(
    content_client, runtime_journal
):
    from tests.integration.test_analysis_observation_inputs import aliases
    from tests.integration.test_content_native_identity import collect
    from tests.unit.test_editorial_native_identity import NOW

    from connections.editorial_services import EditorialSourceService

    engine = content_client.app.state.session_factory.kw["bind"]
    with Session(engine, expire_on_commit=False) as session:
        owner, profile_a, _, target_a, target_b = aliases(session)
        service = EditorialSourceService(session, clock=lambda: NOW)
        profile = service.get_profile(owner_id=owner, profile_id=profile_a.id)
        _, quote = collect(
            session,
            service,
            owner,
            profile,
            body="quote body",
            url="https://www.threads.com/t/QuOtE_01",
        )
        with session.begin():
            source = session.execute(
                text(
                    "SELECT source_native_scope,source_external_id "
                    "FROM content_observations WHERE id=:id"
                ),
                {"id": target_a[2]},
            ).one()
            # Force the other real alias to be the latest; the relation still
            # matches A's exact original identity, not B's canonical record.
            session.execute(
                text(
                    "UPDATE content_observations SET observed_at=:now,received_at=:now WHERE id=:id"
                ),
                {"id": target_b[2], "now": NOW + timedelta(seconds=1)},
            )
            session.execute(
                text(
                    "INSERT INTO content_version_relations "
                    "(id,owner_id,content_version_id,relation_type,"
                    "target_native_scope,target_external_id) "
                    "VALUES (:id,:owner,:version,'quote',:scope,:external)"
                ),
                {
                    "id": uuid4(),
                    "owner": owner,
                    "version": quote[1],
                    "scope": source.source_native_scope,
                    "external": source.source_external_id,
                },
            )
        detail = ContentService(session, clock=lambda: NOW + timedelta(seconds=2)).get_content(
            owner_id=owner, content_id=quote[0]
        )
        assert (
            detail.latest_observation.content_version.relations[0].target_content_id == target_a[0]
        )
        runtime_journal.writer.append(
            command(owner_id=owner, resource_type="content_observation", resource_id=target_a[2])
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session, clock=lambda: NOW + timedelta(seconds=2)).get_content(
                owner_id=owner, content_id=quote[0]
            )


def test_authenticated_detail_keeps_persisted_visibility_and_discovery(detail_context):
    client, factory, _, record, _, _, _ = detail_context
    response = client.get(f"/api/contents/{record.id}")
    assert response.status_code == 200, response.text
    detail = _read(detail_context)
    assert detail.visibility_history and detail.discoveries and detail.version_history
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM content_visibility_observations")) == 1
    with factory() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        ContentService(session).get_content(owner_id=uuid4(), content_id=record.id)
    _deny(detail_context)
    assert client.get(f"/api/contents/{record.id}").status_code == 404
    with factory() as session:
        assert session.scalar(text("SELECT count(*) FROM evidence_deletions")) == 0


@pytest.mark.parametrize("mode", ["ordinary", "old_snapshot", "row_lock", "advisory"])
def test_caller_transaction_is_never_rolled_back_or_admitted(detail_context, monkeypatch, mode):
    _, factory, owner, record, _, _, _ = detail_context
    calls = []
    monkeypatch.setattr(RestrictionJournal, "denied_resources", lambda *_a, **_k: calls.append(1))
    with factory() as session:
        if mode == "old_snapshot":
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        session.execute(
            text(
                "SELECT id FROM content_records FOR UPDATE"
                if mode == "row_lock"
                else "SELECT pg_advisory_xact_lock(898012)"
                if mode == "advisory"
                else "SELECT 1"
            )
        )
        transaction = session.get_transaction()
        with pytest.raises(AuthorityUnavailableError):
            ContentService(session).get_content(owner_id=owner, content_id=record.id)
        assert session.get_transaction() is transaction and transaction.is_active
    assert not calls


def test_external_connection_is_rejected(detail_context):
    _, factory, owner, record, _, _, _ = detail_context
    with (
        factory.kw["bind"].connect() as connection,
        Session(connection) as session,
        pytest.raises(AuthorityUnavailableError),
    ):
        ContentService(session).get_content(owner_id=owner, content_id=record.id)


def test_actual_business_engine_participates_in_independence_check(detail_context):
    client, _, owner, record, _, _, journal = detail_context
    with (
        Session(journal.owner, info={"settings": client.app.state.settings}) as session,
        pytest.raises(AuthorityUnavailableError),
    ):
        ContentService(session).get_content(owner_id=owner, content_id=record.id)


def test_session_advisory_lock_is_rejected_before_journal(detail_context, monkeypatch):
    _, factory, owner, record, _, _, _ = detail_context
    calls = []
    monkeypatch.setattr(RestrictionJournal, "denied_resources", lambda *_a, **_k: calls.append(1))
    engine = create_engine(factory.kw["bind"].url, pool_size=1, max_overflow=0)
    try:
        with Session(engine) as session:
            session.execute(text("SELECT pg_advisory_lock(898013)"))
            session.commit()
            try:
                with pytest.raises(AuthorityUnavailableError):
                    ContentService(session).get_content(owner_id=owner, content_id=record.id)
            finally:
                session.execute(text("SELECT pg_advisory_unlock(898013)"))
                session.commit()
        assert not calls
    finally:
        engine.dispose()


@pytest.mark.parametrize("configuration", ["missing", "partial", "bad_port", "wrong_pin"])
def test_authority_configuration_has_safe_503(detail_context, configuration):
    client, factory, _, record, _, _, _ = detail_context
    updates = {
        "restriction_journal_read_url": None,
        "restriction_journal_ledger_id": None,
        "restriction_journal_epoch": None,
    }
    if configuration == "partial":
        updates["restriction_journal_epoch"] = 1
    elif configuration == "bad_port":
        updates = {
            "restriction_journal_read_url": SecretStr(
                "postgresql+psycopg://private:private@127.0.0.1:invalid/hotkey_test_journal"
            )
        }
    elif configuration == "wrong_pin":
        updates = {"restriction_journal_ledger_id": uuid4()}
    settings = client.app.state.settings.model_copy(update=updates)
    factory.configure(info={"settings": settings})
    response = client.get(f"/api/contents/{record.id}")
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "authority_unavailable"
    assert "private" not in response.text and "postgresql" not in response.text
    assert "retry-after" not in response.headers


def test_transient_authority_has_retry_after(detail_context, monkeypatch):
    client, _, _, record, _, _, _ = detail_context

    def unavailable(*_args, **_kwargs):
        raise AuthorityUnavailableError("transient") from ConnectionError("private credentials")

    monkeypatch.setattr(RestrictionJournal, "denied_resources", unavailable)
    response = client.get(f"/api/contents/{record.id}")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert "private" not in response.text


def test_journal_io_has_no_business_transaction_and_sees_deny_after_p(detail_context, monkeypatch):
    _, factory, owner, record, _, _, _ = detail_context
    actual = RestrictionJournal.denied_resources
    with factory() as session:

        def read(reader, **kwargs):
            assert not session.in_transaction()
            _deny(detail_context)
            return actual(reader, **kwargs)

        monkeypatch.setattr(RestrictionJournal, "denied_resources", read)
        with pytest.raises(ApplicationError, match="resource_not_found"):
            ContentService(session).get_content(owner_id=owner, content_id=record.id)


def test_dependency_change_restarts_with_a_new_journal_snapshot(detail_context, monkeypatch):
    _, factory, _, record, _, policy, _ = detail_context
    actual = RestrictionJournal.denied_resources
    calls = []

    def read(reader, **kwargs):
        calls.append(kwargs["resources"])
        result = actual(reader, **kwargs)
        if len(calls) == 1:
            with factory.begin() as session:
                session.execute(
                    text("UPDATE source_access_policies SET component_version='2' WHERE id=:id"),
                    {"id": policy},
                )
            _deny(detail_context)
        return result

    monkeypatch.setattr(RestrictionJournal, "denied_resources", read)
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)
    assert len(calls) == 2 and ("content_observation", record.latest_observation.id) in calls[1]


def test_unstable_semantics_exhausts_exactly_three_attempts(detail_context, monkeypatch):
    actual = RestrictionJournal.denied_resources
    _, factory, _, _, _, policy, _ = detail_context
    calls = []

    def read(reader, **kwargs):
        calls.append(1)
        result = actual(reader, **kwargs)
        with factory.begin() as session:
            session.execute(
                text("UPDATE source_access_policies SET component_version=:version WHERE id=:id"),
                {"version": str(len(calls) + 1), "id": policy},
            )
        return result

    monkeypatch.setattr(RestrictionJournal, "denied_resources", read)
    with pytest.raises(AuthorityUnavailableError) as captured:
        _read(detail_context)
    assert captured.value.kind == "configuration" and len(calls) == 3


@pytest.mark.parametrize("mutation", ["policy", "visibility", "discovery"])
def test_fresh_v_rejects_changed_or_orphaned_dependencies(detail_context, monkeypatch, mutation):
    _, factory, _, record, _, policy, _ = detail_context
    actual = RestrictionJournal.denied_resources

    def read(reader, **kwargs):
        result = actual(reader, **kwargs)
        with factory.begin() as session:
            if mutation == "policy":
                session.execute(
                    text("UPDATE source_access_policies SET enabled=false WHERE id=:id"),
                    {"id": policy},
                )
            elif mutation == "visibility":
                session.execute(
                    text(
                        "UPDATE content_visibility_observations "
                        "SET source_operation_id=:operation WHERE content_id=:id"
                    ),
                    {"id": record.id, "operation": uuid4()},
                )
            else:
                session.execute(
                    text(
                        "UPDATE content_discoveries "
                        "SET first_observed_at=first_observed_at-interval '1 second' "
                        "WHERE content_id=:id"
                    ),
                    {"id": record.id},
                )
        return result

    monkeypatch.setattr(RestrictionJournal, "denied_resources", read)
    with pytest.raises(ApplicationError, match="resource_not_found"):
        _read(detail_context)


def test_v_rechecks_expiration_with_a_new_clock_value(detail_context, monkeypatch):
    _, factory, owner, record, now, _, _ = detail_context
    actual = RestrictionJournal.denied_resources
    current_time = [now]

    def read(reader, **kwargs):
        result = actual(reader, **kwargs)
        current_time[0] += timedelta(days=31)
        return result

    monkeypatch.setattr(RestrictionJournal, "denied_resources", read)
    with factory() as session, pytest.raises(ApplicationError, match="resource_not_found"):
        ContentService(session, clock=lambda: current_time[0]).get_content(
            owner_id=owner, content_id=record.id
        )
