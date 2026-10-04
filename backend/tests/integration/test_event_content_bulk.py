"""Real observed content: bounded source lookups and fixed comment ALL membership."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from tests.integration.test_analysis_observation_inputs import aliases
from tests.integration.test_content_records import _comment_command, _seed_comment_context
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.integration.test_event_clustering import _add_event_inputs
from tests.integration.test_event_clustering import event_context as event_context
from tests.integration.test_event_reading import _seed_reading
from tests.integration.test_event_reading import event_read_client as event_read_client
from tests.unit.test_editorial_native_identity import NOW

from content.event_reading import load_event_member_content_in_transaction
from content.models import ContentObservation
from content.schemas import EventContentReadReference
from content.services import ContentService, load_event_content_inputs_in_transaction
from evidence.models import EvidenceResource
from evidence.schemas import DeletionReason
from evidence.services import (
    LifecycleService,
    load_readable_resources_in_transaction,
    readable_resource_ids_query,
)


def test_event_source_lookups_use_bounded_queries_for_many_real_observed_versions(event_context):
    sessions, owner, topic, versions, call_id, now = event_context
    with sessions() as session, session.begin():
        extra = _add_event_inputs(session, owner, topic, call_id, now, count=20)
        selected = (*versions[:3], *extra)
        engine = session.get_bind()
        statements = []

        def track(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", track)
        try:
            readings = load_event_content_inputs_in_transaction(
                session, owner_id=owner, version_ids=selected, since=now - timedelta(hours=72)
            )
        finally:
            event.remove(engine, "before_cursor_execute", track)
        assert set(readings) == set(selected)
        assert len(statements) <= 10
        observations = {
            row.content_version_id: row.id
            for row in session.scalars(
                select(ContentObservation).where(
                    ContentObservation.owner_id == owner,
                    ContentObservation.content_version_id.in_(selected),
                )
            )
        }
        assert all(
            item.observation_id == observations[version] for version, item in readings.items()
        )
        assert all(item.first_seen_at >= now - timedelta(hours=72) for item in readings.values())
        assert (
            load_event_content_inputs_in_transaction(
                session, owner_id=uuid4(), version_ids=selected, since=now - timedelta(hours=72)
            )
            == {}
        )


def test_fixed_event_comment_cannot_be_read_when_missing_from_declared_actual_inputs(
    event_read_client,
):
    owner, _, _, fixed, _ = _seed_reading(event_read_client)
    with event_read_client.app.state.session_factory() as session:
        connection = session.execute(text("SELECT id FROM source_connections")).scalar_one()
    policy, retention, job = _seed_comment_context(event_read_client, owner, connection)
    with event_read_client.app.state.session_factory() as session:
        comment = ContentService(session).persist_comment(
            owner_id=owner,
            command=_comment_command(
                owner_id=owner,
                connection_id=connection,
                policy_id=policy,
                retention_id=retention,
                job_id=job,
                external_id="fixed-comment-outside-manifest",
                post_external_id=fixed.external_id,
            ),
        )
    assert fixed.latest_observation.content_version is not None
    reference = EventContentReadReference(
        content_id=fixed.id,
        content_version_id=fixed.latest_observation.content_version.id,
        observation_id=fixed.latest_observation.id,
        representative_comment_id=comment.id,
        representative_comment_observation_id=comment.latest_observation.id,
        input_observation_ids=(fixed.latest_observation.id,),
    )
    with event_read_client.app.state.session_factory() as session, session.begin():
        missing = load_event_member_content_in_transaction(
            session, owner_id=owner, references=(reference,), now=datetime.now(UTC)
        )[reference]
        assert missing.representative_comment_state == "unavailable"
        assert missing.representative_comment is None
        complete = replace(
            reference,
            input_observation_ids=(fixed.latest_observation.id, comment.latest_observation.id),
        )
        allowed = load_event_member_content_in_transaction(
            session, owner_id=owner, references=(complete,), now=datetime.now(UTC)
        )[complete]
        assert allowed.representative_comment_state == "readable"
        assert allowed.representative_comment.observation.id == comment.latest_observation.id


def test_flat_original_evidence_projection_preserves_current_exclusions_and_bounded_all(engine):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            ids = {a[2], b[2]}
            before = load_readable_resources_in_transaction(
                session,
                owner_id=owner,
                resource_type="content_observation",
                resource_ids=ids,
                now=NOW,
            )
            assert set(before) == ids
            assert (
                load_readable_resources_in_transaction(
                    session,
                    owner_id=uuid4(),
                    resource_type="content_observation",
                    resource_ids=ids,
                    now=NOW,
                )
                == {}
            )
            assert (
                load_readable_resources_in_transaction(
                    session,
                    owner_id=owner,
                    resource_type="content_version",
                    resource_ids=ids,
                    now=NOW,
                )
                == {}
            )
            with pytest.raises(ValueError, match="bounded caller transaction"):
                load_readable_resources_in_transaction(
                    session,
                    owner_id=owner,
                    resource_type="content_observation",
                    resource_ids={uuid4() for _ in range(1001)},
                    now=NOW,
                )
            statement = (
                readable_resource_ids_query(
                    owner_id=owner, resource_type="content_observation", now=NOW
                )
                .where(EvidenceResource.resource_id.in_(ids | {uuid4() for _ in range(98)}))
                .with_only_columns(EvidenceResource)
            )
            sql = str(
                statement.compile(
                    dialect=session.get_bind().dialect, compile_kwargs={"literal_binds": True}
                )
            )
            plan = session.connection().exec_driver_sql("EXPLAIN (FORMAT JSON) " + sql).scalar_one()
            nodes, pending = [], [plan[0]["Plan"]]
            while pending:
                node = pending.pop()
                nodes.append(node)
                pending.extend(node.get("Plans", ()))
            assert not any(node.get("Join Type") == "Semi" for node in nodes)
            assert sum(node.get("Relation Name") == "evidence_resources" for node in nodes) == 1
            session.execute(
                text(
                    "UPDATE evidence_resources SET expires_at=:now "
                    "WHERE owner_id=:owner AND resource_type='content_observation' "
                    "AND resource_id=:id"
                ),
                {"now": NOW, "owner": owner, "id": a[2]},
            )
            assert set(
                load_readable_resources_in_transaction(
                    session,
                    owner_id=owner,
                    resource_type="content_observation",
                    resource_ids=ids,
                    now=NOW,
                )
            ) == {b[2]}
        LifecycleService(session, clock=lambda: NOW).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=b[2],
            reason=DeletionReason.USER_REQUEST,
        )
        with session.begin():
            assert (
                load_readable_resources_in_transaction(
                    session,
                    owner_id=owner,
                    resource_type="content_observation",
                    resource_ids=ids,
                    now=NOW,
                )
                == {}
            )
