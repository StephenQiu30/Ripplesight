from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from tests.conftest import TEST_DATABASE_TRUNCATE

from connections.presets import SOURCE_PRESETS
from connections.services import (
    SourcePresetService,
    pause_bilibili_connection_in_transaction,
)
from core.config import Settings
from core.errors import ApplicationError
from db.demo import resolve_demo_scope
from jobs.schemas import JobAcceptanceInput
from jobs.services import JobService
from main import create_app
from monitors.services import MonitorTopicService
from sources.contracts import SourceCapability, SourceStopReason

_TRUNCATE = TEST_DATABASE_TRUNCATE


@pytest.fixture
def monitor_topic_client() -> Iterator[TestClient]:
    database_url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("HOTKEY_TEST_DATABASE_URL is required for PostgreSQL integration tests")

    settings = Settings(
        environment="test",
        log_level="WARNING",
        database_url=database_url,
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(_TRUNCATE))
    try:
        with TestClient(create_app(settings)) as client:
            yield client
    finally:
        with engine.begin() as connection:
            connection.execute(text(_TRUNCATE))
        engine.dispose()


def _demo_scope(client: TestClient) -> UUID:
    with client.app.state.session_factory() as session:
        return resolve_demo_scope(session)


def _csrf_headers(client: TestClient) -> dict[str, str]:
    return {"X-HotKey-CSRF": "1"}


def _topic_payload() -> dict[str, object]:
    return {
        "name": "  品牌\t召回  ",
        "match_any": ["Brand", "\uff22\uff32\uff21\uff2e\uff24"],
        "match_all": ["召回"],
        "exclude": ["招聘"],
    }


def test_topic_create_edit_and_reopen_preserve_immutable_versions(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)

    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json=_topic_payload(),
    )
    assert created.status_code == 201, created.json()
    assert created.headers["location"] == f"/api/topics/{created.json()['id']}"
    assert created.headers["cache-control"] == "no-store"
    assert created.json()["name"] == "品牌 召回"
    assert created.json()["status"] == "paused"
    assert created.json()["readiness_status"] == "pending_source_selection"
    assert created.json()["current_version"] == 1
    assert created.json()["rules"] == {
        "match_any": ["Brand"],
        "match_all": ["召回"],
        "exclude": ["招聘"],
    }
    assert "owner_id" not in created.json()

    updated = monitor_topic_client.patch(
        created.headers["location"],
        headers=_csrf_headers(monitor_topic_client),
        json={
            **_topic_payload(),
            "expected_version": 1,
            "match_any": ["Brand", "厂商"],
        },
    )

    assert updated.status_code == 200, updated.json()
    assert updated.json()["current_version"] == 2
    reopened = monitor_topic_client.get(created.headers["location"])
    assert reopened.status_code == 200
    assert reopened.json() == updated.json()

    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        versions = session.execute(
            text(
                "SELECT version, match_any FROM monitor_topic_versions "
                "WHERE topic_id = :topic_id ORDER BY version"
            ),
            {"topic_id": created.json()["id"]},
        ).all()
    assert versions == [(1, ["Brand"]), (2, ["Brand", "厂商"])]


def test_stale_topic_edit_conflicts_without_partial_version(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json=_topic_payload(),
    )
    location = created.headers["location"]

    first = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "expected_version": 1, "exclude": ["招聘", "校招"]},
    )
    stale = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "expected_version": 1, "exclude": ["广告"]},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["code"] == "topic_version_conflict"
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM monitor_topic_versions WHERE topic_id = :topic_id"),
                {"topic_id": created.json()["id"]},
            ).scalar_one()
            == 2
        )


def test_source_and_interval_changes_create_immutable_topic_snapshots(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = resolve_demo_scope(session)
        SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["hackernews"]
        )
    created = monitor_topic_client.post(
        "/api/topics", headers=_csrf_headers(monitor_topic_client), json=_topic_payload()
    )
    location = created.headers["location"]
    updated = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={
            **_topic_payload(),
            "expected_version": 1,
            "source_keys": ["hackernews"],
            "collection_interval_seconds": 600,
        },
    )
    assert updated.status_code == 200, updated.json()
    assert updated.json()["current_version"] == 2
    assert updated.json()["source_keys"] == ["hackernews"]
    assert updated.json()["collection_interval_seconds"] == 600
    with factory() as session:
        versions = session.execute(
            text(
                "SELECT version, source_keys, collection_interval_seconds "
                "FROM monitor_topic_versions WHERE topic_id = :id ORDER BY version"
            ),
            {"id": created.json()["id"]},
        ).all()
    assert versions == [(1, [], 1800), (2, ["hackernews"], 600)]
    stale = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "expected_version": 1},
    )
    assert stale.status_code == 409
    assert monitor_topic_client.get(location).json() == updated.json()


def test_unapplied_search_source_cannot_be_selected_or_resumed(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    rejected = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "source_keys": ["hackernews"]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "source_preset_not_applied"
    with monitor_topic_client.app.state.session_factory() as session:
        assert session.execute(text("SELECT count(*) FROM monitor_topics")).scalar_one() == 0


def test_source_selection_rejects_revoked_access_policy(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = resolve_demo_scope(session)
        SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["hackernews"]
        )
        session.execute(
            text(
                "UPDATE source_access_policies SET enabled = false "
                "WHERE owner_id = :owner_id AND source_key = 'hackernews' "
                "AND capability = 'search'"
            ),
            {"owner_id": owner_id},
        )
    rejected = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "source_keys": ["hackernews"]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "source_preset_not_applied"


def test_resume_rejects_unavailable_source_budget(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = resolve_demo_scope(session)
        SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["hackernews"]
        )
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "source_keys": ["hackernews"]},
    )
    assert created.status_code == 201, created.json()
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE owner_id = :owner_id AND budget_key = 'source.hackernews.network.daily'"
            ),
            {"owner_id": owner_id},
        )
    rejected = monitor_topic_client.post(
        f"{created.headers['location']}/resume",
        headers=_csrf_headers(monitor_topic_client),
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "topic_not_ready"
    assert monitor_topic_client.get(created.headers["location"]).json()["status"] == "paused"


def test_active_topic_cannot_enable_a_new_source_without_budget(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = resolve_demo_scope(session)
        for source_key in ("hackernews", "google_news"):
            SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=SOURCE_PRESETS[source_key]
            )
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "source_keys": ["hackernews"]},
    )
    assert created.status_code == 201, created.json()
    location = created.headers["location"]
    resumed = monitor_topic_client.post(
        f"{location}/resume", headers=_csrf_headers(monitor_topic_client)
    )
    assert resumed.status_code == 200, resumed.json()
    with factory.begin() as session:
        session.execute(
            text(
                "UPDATE resource_budget_policies SET enabled = false "
                "WHERE owner_id = :owner_id AND budget_key = 'source.google_news.network.daily'"
            ),
            {"owner_id": owner_id},
        )
    rejected = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={
            **_topic_payload(),
            "expected_version": 1,
            "source_keys": ["google_news", "hackernews"],
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "topic_not_ready"
    current = monitor_topic_client.get(location)
    assert current.json()["current_version"] == 1
    assert current.json()["source_keys"] == ["hackernews"]
    with factory() as session:
        events = session.execute(
            text(
                "SELECT status, reason FROM monitor_topic_status_events "
                "WHERE topic_id = :topic_id ORDER BY event_sequence"
            ),
            {"topic_id": created.json()["id"]},
        ).all()
    assert events == [("paused", "created"), ("active", "resumed")]


def test_name_only_edit_keeps_rule_version_and_owner_filter_hides_topic(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json=_topic_payload(),
    )

    renamed = monitor_topic_client.patch(
        created.headers["location"],
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "name": "品牌召回监控", "expected_version": 1},
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "品牌召回监控"
    assert renamed.json()["current_version"] == 1
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM monitor_topic_versions WHERE topic_id = :topic_id"),
                {"topic_id": created.json()["id"]},
            ).scalar_one()
            == 1
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM monitor_topic_status_events WHERE topic_id = :topic_id"),
                {"topic_id": created.json()["id"]},
            ).scalar_one()
            == 1
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            MonitorTopicService(session).get_topic(
                owner_id=uuid4(),
                topic_id=created.json()["id"],
            )


def test_conflicting_keyword_groups_are_rejected_without_persistence(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)

    rejected = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "exclude": [" brand "]},
    )

    assert rejected.status_code == 422
    assert rejected.json()["code"] == "keyword_group_conflict"
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM monitor_topics")).scalar_one() == 0


def test_topic_routes_enforce_csrf_and_hidden_missing_boundary(
    monitor_topic_client: TestClient,
) -> None:
    assert monitor_topic_client.get("/api/topics").status_code == 200

    _demo_scope(monitor_topic_client)
    missing_csrf = monitor_topic_client.post("/api/topics", json=_topic_payload())
    assert missing_csrf.status_code == 403
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json=_topic_payload(),
    )
    clone_without_csrf = monitor_topic_client.post(f"{created.headers['location']}/clone")
    assert clone_without_csrf.status_code == 403
    missing = monitor_topic_client.get(f"/api/topics/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "resource_not_found"


def test_topic_list_clone_and_archive_keep_independent_history(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json=_topic_payload(),
    )
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        owner_id = resolve_demo_scope(session)
        JobService(session).accept(
            owner_id=owner_id,
            command=JobAcceptanceInput(
                operation_id=uuid4(),
                kind="monitor.collect",
                observation={
                    "configuration_ref": f"topic:{created.json()['id']}",
                    "configuration_version": 1,
                    "source_key": "x",
                    "source_capability": SourceCapability.SEARCH,
                },
                scope={"query": "brand"},
            ),
        )

    listed = monitor_topic_client.get("/api/topics")
    cloned = monitor_topic_client.post(
        f"{created.headers['location']}/clone",
        headers=_csrf_headers(monitor_topic_client),
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
    assert cloned.status_code == 201
    assert cloned.json()["id"] != created.json()["id"]
    assert cloned.json()["status"] == "paused"
    assert cloned.json()["current_version"] == 1
    assert cloned.json()["rules"] == created.json()["rules"]
    with factory() as session:
        clone_events = session.execute(
            text(
                "SELECT event_sequence, status, reason, topic_rule_version "
                "FROM monitor_topic_status_events WHERE topic_id = :topic_id"
            ),
            {"topic_id": cloned.json()["id"]},
        ).all()
    assert clone_events == [(1, "paused", "cloned", 1)]
    first_page = monitor_topic_client.get("/api/topics?limit=1")
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 1
    assert first_page.json()["next_cursor"] is not None
    second_page = monitor_topic_client.get(
        "/api/topics",
        params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
    )
    assert second_page.status_code == 200
    assert second_page.json()["next_cursor"] is None
    assert {
        first_page.json()["items"][0]["id"],
        second_page.json()["items"][0]["id"],
    } == {created.json()["id"], cloned.json()["id"]}
    with factory() as session:
        jobs = session.execute(text("SELECT configuration_ref FROM jobs")).scalars().all()
    assert jobs == [f"topic:{created.json()['id']}"]

    archived = monitor_topic_client.post(
        f"{created.headers['location']}/archive",
        headers=_csrf_headers(monitor_topic_client),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    visible = monitor_topic_client.get("/api/topics")
    assert [item["id"] for item in visible.json()["items"]] == [cloned.json()["id"]]
    with_archived = monitor_topic_client.get("/api/topics?include_archived=true")
    assert {item["id"] for item in with_archived.json()["items"]} == {
        created.json()["id"],
        cloned.json()["id"],
    }


def test_topic_lifecycle_is_idempotent_and_resume_requires_ready_source(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json=_topic_payload(),
    )
    location = created.headers["location"]

    paused = monitor_topic_client.post(
        f"{location}/pause",
        headers=_csrf_headers(monitor_topic_client),
    )
    resumed = monitor_topic_client.post(
        f"{location}/resume",
        headers=_csrf_headers(monitor_topic_client),
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert resumed.status_code == 409
    assert resumed.json()["code"] == "topic_not_ready"
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = resolve_demo_scope(session)
        SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["hackernews"]
        )
    selected = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "expected_version": 1, "source_keys": ["hackernews"]},
    )
    assert selected.status_code == 200
    resumed_ready = monitor_topic_client.post(
        f"{location}/resume",
        headers=_csrf_headers(monitor_topic_client),
    )
    with factory() as session:
        first_schedule_updated_at = session.execute(
            text("SELECT updated_at FROM monitor_schedules WHERE topic_id = :topic_id"),
            {"topic_id": created.json()["id"]},
        ).scalar_one()
    resumed_again = monitor_topic_client.post(
        f"{location}/resume",
        headers=_csrf_headers(monitor_topic_client),
    )
    with factory() as session:
        second_schedule_updated_at = session.execute(
            text("SELECT updated_at FROM monitor_schedules WHERE topic_id = :topic_id"),
            {"topic_id": created.json()["id"]},
        ).scalar_one()
    paused_again = monitor_topic_client.post(
        f"{location}/pause",
        headers=_csrf_headers(monitor_topic_client),
    )
    assert resumed_ready.status_code == 200
    assert resumed_ready.json()["status"] == "active"
    assert resumed_again.status_code == 200
    assert resumed_again.json()["updated_at"] == resumed_ready.json()["updated_at"]
    assert second_schedule_updated_at == first_schedule_updated_at
    assert paused_again.status_code == 200
    assert paused_again.json()["status"] == "paused"
    archived = monitor_topic_client.post(
        f"{location}/archive",
        headers=_csrf_headers(monitor_topic_client),
    )
    archived_again = monitor_topic_client.post(
        f"{location}/archive",
        headers=_csrf_headers(monitor_topic_client),
    )
    edit_archived = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "expected_version": 1},
    )
    assert archived.status_code == 200
    assert archived_again.status_code == 200
    assert archived_again.json()["status"] == "archived"
    assert edit_archived.status_code == 409
    assert edit_archived.json()["code"] == "topic_archived"
    resume_archived = monitor_topic_client.post(
        f"{location}/resume", headers=_csrf_headers(monitor_topic_client)
    )
    assert resume_archived.status_code == 409
    assert resume_archived.json()["code"] == "topic_archived"
    with factory() as session:
        events = session.execute(
            text(
                "SELECT event_sequence, status, reason, topic_rule_version, occurred_at "
                "FROM monitor_topic_status_events "
                "WHERE topic_id = :topic_id ORDER BY event_sequence"
            ),
            {"topic_id": created.json()["id"]},
        ).all()
    assert [tuple(event[:4]) for event in events] == [
        (1, "paused", "created", 1),
        (2, "active", "resumed", 2),
        (3, "paused", "paused", 2),
        (4, "archived", "archived", 2),
    ]
    assert events[0].occurred_at == datetime.fromisoformat(created.json()["created_at"])
    assert [event.occurred_at for event in events] == sorted(event.occurred_at for event in events)
    separate_process = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import sys
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
with engine.connect() as connection:
    states = connection.execute(
        text("SELECT status FROM monitor_topic_status_events "
             "WHERE topic_id = :topic_id ORDER BY event_sequence"),
        {"topic_id": sys.argv[1]},
    ).scalars().all()
print(",".join(states))
""",
            created.json()["id"],
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert separate_process.stdout.strip() == "paused,active,paused,archived"


def test_removing_all_sources_records_automatic_topic_pause(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = resolve_demo_scope(session)
        SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["hackernews"]
        )
    created = monitor_topic_client.post(
        "/api/topics",
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "source_keys": ["hackernews"]},
    )
    assert created.status_code == 201, created.json()
    location = created.headers["location"]
    resumed = monitor_topic_client.post(
        location + "/resume", headers=_csrf_headers(monitor_topic_client)
    )
    assert resumed.status_code == 200, resumed.json()
    selected_none = monitor_topic_client.patch(
        location,
        headers=_csrf_headers(monitor_topic_client),
        json={**_topic_payload(), "expected_version": 1, "source_keys": []},
    )
    assert selected_none.status_code == 200, selected_none.json()
    assert selected_none.json()["status"] == "paused"
    assert selected_none.json()["current_version"] == 2
    with factory() as session:
        events = session.execute(
            text(
                "SELECT event_sequence, status, reason, topic_rule_version "
                "FROM monitor_topic_status_events WHERE topic_id = :topic_id "
                "ORDER BY event_sequence"
            ),
            {"topic_id": created.json()["id"]},
        ).all()
    assert events == [
        (1, "paused", "created", 1),
        (2, "active", "resumed", 1),
        (3, "paused", "source_selection", 2),
    ]


def test_topic_preview_is_local_explainable_and_side_effect_free(
    monitor_topic_client: TestClient,
) -> None:
    payload = {
        "match_any": [" Brand ", "\uff22\uff32\uff21\uff2e\uff24"],
        "match_all": ["召回"],
        "exclude": ["招聘"],
        "sample_titles": ["brand 召回招聘", "BRAND 召回公告"],
    }
    missing_session = monitor_topic_client.post(
        "/api/topics/preview",
        headers={"X-HotKey-CSRF": "1"},
        json=payload,
    )
    assert missing_session.status_code == 200
    _demo_scope(monitor_topic_client)

    preview = monitor_topic_client.post(
        "/api/topics/preview",
        headers=_csrf_headers(monitor_topic_client),
        json=payload,
    )

    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "no-store"
    assert preview.json() == {
        "rules": {
            "match_any": ["Brand"],
            "match_all": ["召回"],
            "exclude": ["招聘"],
        },
        "samples": [
            {
                "sample_index": 0,
                "matched": False,
                "matched_any": ["Brand"],
                "matched_all": ["召回"],
                "excluded_by": ["招聘"],
            },
            {
                "sample_index": 1,
                "matched": True,
                "matched_any": ["Brand"],
                "matched_all": ["召回"],
                "excluded_by": [],
            },
        ],
        "expansion": {
            "local_alias_external_queries": 0,
            "local_alias_budget_units": 0,
            "upstream_status": "pending_source_selection",
            "upstream_external_queries": None,
            "upstream_budget_units": None,
        },
    }
    without_csrf = monitor_topic_client.post(
        "/api/topics/preview",
        json={
            "match_any": ["品牌"],
            "match_all": [],
            "exclude": [],
            "sample_titles": ["品牌公告"],
        },
    )
    assert without_csrf.status_code == 403
    factory = monitor_topic_client.app.state.session_factory
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM monitor_topics")).scalar_one() == 0
        assert (
            session.execute(text("SELECT count(*) FROM monitor_topic_versions")).scalar_one() == 0
        )
        assert session.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 0


def test_every_builtin_source_preset_applies_against_the_real_schema(
    monitor_topic_client: TestClient,
) -> None:
    """Preset config keys and capabilities must satisfy the database CHECK constraints."""
    _demo_scope(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    for preset in SOURCE_PRESETS.values():
        with factory.begin() as session:
            owner_id = resolve_demo_scope(session)
            applied = SourcePresetService(session).apply_in_transaction(
                owner_id=owner_id, preset=preset
            )
        assert applied.source_key == preset.source_key


def test_bilibili_pause_is_not_cleared_by_preset_reapply(
    monitor_topic_client: TestClient,
) -> None:
    _demo_scope(monitor_topic_client)
    factory = monitor_topic_client.app.state.session_factory
    with factory.begin() as session:
        owner_id = resolve_demo_scope(session)
        applied = SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["bilibili"]
        )
    with factory.begin() as session:
        pause_bilibili_connection_in_transaction(
            session,
            owner_id=owner_id,
            connection_id=applied.connection_id,
            connection_version=applied.connection_version,
            now=datetime.now(UTC),
            reason=SourceStopReason.AUTHENTICATION_REQUIRED,
            trigger_job_id=uuid4(),
        )
    with factory() as session:
        assert (
            session.execute(
                text("SELECT status FROM source_connections WHERE id = :connection_id"),
                {"connection_id": applied.connection_id},
            ).scalar_one()
            == "disabled"
        )
    with pytest.raises(ApplicationError, match="connection_disabled"), factory.begin() as session:
        SourcePresetService(session).apply_in_transaction(
            owner_id=owner_id, preset=SOURCE_PRESETS["bilibili"]
        )
    with factory() as session:
        assert (
            session.execute(
                text("SELECT current_version FROM source_connections WHERE id = :id"),
                {"id": applied.connection_id},
            ).scalar_one()
            == applied.connection_version
        )
