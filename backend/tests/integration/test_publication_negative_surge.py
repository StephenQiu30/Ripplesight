"""Persist real analysis dimensions and prove public rule decisions without external calls."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from tests.integration import test_publication_home as home_fixture
from tests.integration import test_publication_sentiment as sentiment_fixture
from tests.integration.test_publication import editorial_client as editorial_client
from tests.unit.test_publication_negative_surge import policy

from publication.schemas import PublicationOverrideInput
from publication.services import PublicationService


def seed_surge(client, monkeypatch):
    """Two fixed public reports, one per window, with actual producer persistence."""
    from tests.integration.test_publication import NOW

    monkeypatch.setattr(home_fixture, "NOW", NOW)
    owner, posts, events = home_fixture._seed_events(client, 1, with_development=True)
    with client.app.state.session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE jobs SET scope=scope || "
                '\'{"scan_kind":"new_scan"}\'::jsonb '
                "WHERE owner_id=:owner AND source_key IS NOT NULL"
            ),
            {"owner": owner},
        )
        for index, hours in [(0, 25), (1, 1)]:
            session.execute(
                text("UPDATE content_versions SET created_at=:at WHERE content_id=:id"),
                {"at": NOW - timedelta(hours=hours), "id": posts[index].id},
            )
            session.execute(
                text(
                    "UPDATE content_observations SET received_at=:at, observed_at=:at "
                    "WHERE content_id=:id"
                ),
                {"at": NOW - timedelta(hours=hours), "id": posts[index].id},
            )
    sentiment_fixture._annotate(client, owner, posts[0], NOW, sentiment="neutral")
    sentiment_fixture._annotate(client, owner, posts[1], NOW, sentiment="negative")
    client.app.state.settings.public_negative_surge_policy = policy(
        min_valid_samples=1, min_negative_count=1, min_ratio_increase=1.0
    )
    return owner, posts, events, NOW


@pytest.mark.parametrize(
    "changes,expected,reason",
    [
        ({}, "triggered", None),
        ({"min_negative_count": 2}, "not_triggered", "negative_count_below_threshold"),
        ({"min_valid_samples": 2}, "insufficient_data", "previous_samples_insufficient"),
    ],
)
def test_actual_producer_pg_permission_api_rule_chain(
    editorial_client, monkeypatch, changes, expected, reason
):
    client = editorial_client
    _owner, posts, events, _now = seed_surge(client, monkeypatch)
    original = client.app.state.settings.public_negative_surge_policy
    client.app.state.settings.public_negative_surge_policy = original.model_copy(update=changes)
    before = counts(client)
    response = client.get("/api/publication/home?limit=1")
    assert response.status_code == 200, response.text
    body = response.json()
    surge = body["negative_surge"]
    assert surge["state"] == expected and surge["total_events"] == 1
    event = surge["events"][0]
    assert event["event_id"] == str(events[0]) and event["state"] == expected
    assert event["current"]["valid_count"] == event["previous"]["valid_count"] == 1
    assert event["current"]["negative"] == 1 and event["previous"]["negative"] == 0
    assert "calibration_reference" not in response.text
    assert original.calibration_reference.get_secret_value() not in response.text
    assert body["overview"]["negative_surge_count"] == (
        None if expected == "insufficient_data" else int(expected == "triggered")
    )
    if reason:
        assert reason in event["reasons"]
    detail = client.get(f"/api/publication/stories/{events[0]}").json()
    assert {report["id"] for report in detail["reports"]} == {str(post.id) for post in posts}
    assert counts(client) == before


def counts(client):
    with client.app.state.session_factory.begin() as session:
        return {
            table: session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in [
                "jobs",
                "ai_calls",
                "content_annotations",
                "publication_revisions",
                "alert_evaluations",
                "notification_deliveries",
            ]
        }


def test_rule_absent_reports_data_gaps_and_revocation_removes_prior_trigger(
    editorial_client, monkeypatch
):
    client = editorial_client
    owner, posts, events, now = seed_surge(client, monkeypatch)
    before = client.get("/api/publication/home").json()
    assert before["negative_surge"]["triggered_count"] == 1
    client.app.state.settings.public_negative_surge_policy = None
    absent = client.get("/api/publication/home").json()
    assert absent["negative_surge"]["state"] == "not_configured"
    assert absent["overview"]["negative_surge_count"] is None
    with client.app.state.session_factory.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            content_id=posts[0].id,
            actor_id=owner,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="withdrawn",
                reason="controlled revoke",
            ),
            now=now,
        )
    client.app.state.settings.public_negative_surge_policy = policy(
        min_valid_samples=1, min_negative_count=1
    )
    after = client.get("/api/publication/home").json()
    assert after["negative_surge"]["state"] == "empty"
    assert (
        after["negative_surge"]["total_events"] == after["negative_surge"]["triggered_count"] == 0
    )
    assert after["negative_surge"]["events"] == []
    assert client.get(f"/api/publication/stories/{events[0]}").status_code == 404


def test_unknown_collection_provenance_is_unavailable_not_clear(editorial_client, monkeypatch):
    owner, _posts, _events, _now = seed_surge(editorial_client, monkeypatch)
    with editorial_client.app.state.session_factory.begin() as session:
        session.execute(
            text("UPDATE jobs SET scope=scope - 'scan_kind' WHERE owner_id=:owner"),
            {"owner": owner},
        )
    response = editorial_client.get("/api/publication/home")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["negative_surge"]["state"] == "unavailable"
    assert "analysis_unavailable" in body["negative_surge"]["events"][0]["reasons"]
    assert body["overview"]["negative_surge_count"] is None
