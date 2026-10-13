"""Real heat writer to PostgreSQL to public HTTP, without external service calls."""

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from tests.integration.test_editorial_execution import NOW
from tests.integration.test_publication import editorial_client as _publication_client
from tests.integration.test_publication_home import _seed_events

from events.heat import EventHeatService
from events.heat_models import EventAttentionSnapshot
from events.heat_schemas import ATTENTION_FORMULA_VERSION, AttentionSourceInput
from publication.application import PublicationApplicationService
from publication.schemas import PublicationOverrideInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client(request, monkeypatch):
    """Keep shared event-seed clocks aligned even late in a full regression."""
    import tests.integration.test_publication_home as home_seed

    fixture = _publication_client.__wrapped__(request, monkeypatch)
    client = next(fixture)
    monkeypatch.setattr(home_seed, "NOW", NOW)
    try:
        yield client
    finally:
        fixture.close()


def seed_history(client):
    owner, posts, events = _seed_events(client, 1, with_development=True)
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE content_observations SET author_external_id='second-author' "
                "WHERE content_id=:id"
            ),
            {"id": posts[-1].id},
        )
    with sessions() as session:
        service = EventHeatService(session, clock=lambda: NOW)
        for kind, ref, mode in (
            ("source", "x", "editorial"),
            ("author", "second-author", "signal"),
        ):
            service.upsert_source(
                owner_id=owner,
                command=AttentionSourceInput(
                    source_key="x",
                    selector_kind=kind,
                    selector_ref=ref,
                    name="controlled private source",
                    mode=mode,
                    scheduled=False,
                ),
            )
    first = NOW.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    for index in range(7):
        at = first + timedelta(hours=index)
        with sessions.begin() as session:
            result = EventHeatService(
                session, clock=lambda at=at: at + timedelta(minutes=10)
            ).refresh_in_transaction(owner_id=owner, event_id=events[0], at=at)
            assert result.complete and result.eligible
    return owner, posts, events[0], first + timedelta(hours=6, minutes=20)


def test_heat_writer_public_http_and_immediate_permission_revocation(editorial_client, monkeypatch):
    import publication.application as application

    owner, posts, event, now = seed_history(editorial_client)
    sessions = editorial_client.app.state.session_factory

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(application, "datetime", Clock)

    def counts():
        with sessions.begin() as session:
            return tuple(
                session.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in (
                    "jobs",
                    "event_attention_snapshots",
                    "publication_revisions",
                    "alert_evaluations",
                    "notification_deliveries",
                )
            )

    before = counts()
    response = editorial_client.get("/api/publication/home")
    assert response.status_code == 200, response.text
    history = response.json()["stories"][0]["history"]
    assert history["state"] == "available" and history["trend"]["state"] == "available"
    assert history["trend"]["direction"] == "down" and history["trend"]["percent"] < 0
    assert len([p for p in history["points"] if p["value"] is not None]) == 7
    assert history["time_basis"] == "delayed_hourly_calculation"
    assert "controlled private source" not in str(history)
    detail = editorial_client.get(f"/api/publication/stories/{event}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["history"] == history
    assert counts() == before
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=posts[0].id,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=1,
                visibility="withdrawn",
                reason="controlled withdrawal",
            ),
            now=now,
        )
    response = editorial_client.get("/api/publication/home")
    assert response.status_code == 200 and response.json()["stories"] == []


def test_newest_recomputation_and_missing_slot_do_not_reuse_older_record(editorial_client):
    owner, _, event, now = seed_history(editorial_client)
    sessions = editorial_client.app.state.session_factory
    at = now.replace(minute=0, second=0, microsecond=0)
    with sessions.begin() as session:
        EventHeatService(session, clock=lambda: now).refresh_in_transaction(
            owner_id=owner, event_id=event, at=at, historical=True
        )
    with sessions() as session:
        home = PublicationApplicationService(session).home(owner_id=owner, now=now)
        history = home.stories[0].history
        assert history.trend.reason == "recomputed" and history.points[-1].value is None
    with sessions.begin() as session:
        session.execute(
            delete(EventAttentionSnapshot).where(
                EventAttentionSnapshot.event_id == event,
                EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
                EventAttentionSnapshot.window_end == at - timedelta(hours=2),
            )
        )
    with sessions() as session:
        history = (
            PublicationApplicationService(session).home(owner_id=owner, now=now).stories[0].history
        )
        assert history.points[-3].reason == "missing"


def test_writer_accepts_noncontributing_material_received_after_window(editorial_client):
    owner, _, event, now = seed_history(editorial_client)
    sessions = editorial_client.app.state.session_factory
    at = now.replace(minute=0, second=0, microsecond=0)
    # Both fixed reports are later than this cutoff, so the writer legitimately
    # excludes them. This checks time provenance independently of eligibility.
    with sessions.begin() as session:
        session.execute(
            text("UPDATE content_observations SET published_at=:at WHERE owner_id=:owner"),
            {"at": at + timedelta(minutes=5), "owner": owner},
        )
        result = EventHeatService(session, clock=lambda: now).refresh_in_transaction(
            owner_id=owner, event_id=event, at=at
        )
        assert result.heat == 0 and not result.eligible
    with sessions() as session:
        history = (
            PublicationApplicationService(session).home(owner_id=owner, now=now).stories[0].history
        )
        assert history.points[-1].reason == "incomplete"
        assert history.points[-1].computed_at == now


def test_capacity_2000_and_2001_is_checked_before_latest_hour_dedup(editorial_client):
    owner, _, event, now = seed_history(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        row = session.scalar(
            select(EventAttentionSnapshot)
            .where(
                EventAttentionSnapshot.event_id == event,
                EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
            )
            .order_by(EventAttentionSnapshot.window_end.desc())
        )
        base = {
            column.name: copy.deepcopy(getattr(row, column.name))
            for column in EventAttentionSnapshot.__table__.columns
        }
        additions = []
        for index in range(1994):
            item = copy.deepcopy(base)
            item["id"] = uuid4()
            item["computed_at"] = base["computed_at"] + timedelta(microseconds=index + 1)
            item["input_manifest"]["controlled_nonce"] = index
            item["input_fingerprint"] = hashlib.sha256(
                json.dumps(item["input_manifest"], sort_keys=True, separators=(",", ":")).encode()
            ).digest()
            additions.append(item)
        session.execute(EventAttentionSnapshot.__table__.insert(), additions[:-1])
    with sessions() as session:
        assert (
            PublicationApplicationService(session)
            .home(owner_id=owner, now=now)
            .stories[0]
            .history.state
            == "available"
        )
    with sessions.begin() as session:
        session.execute(EventAttentionSnapshot.__table__.insert(), additions[-1:])
    with sessions() as session:
        history = (
            PublicationApplicationService(session).home(owner_id=owner, now=now).stories[0].history
        )
        assert history.state == "unavailable" and history.reason == "capacity"
        assert all(point.value is None and point.reason == "capacity" for point in history.points)


@pytest.mark.parametrize("bad", ["hash", "permission"])
def test_newest_bad_basis_does_not_fall_back_to_a_good_row(editorial_client, bad):
    owner, _, event, now = seed_history(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        row = session.scalar(
            select(EventAttentionSnapshot)
            .where(
                EventAttentionSnapshot.event_id == event,
                EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
            )
            .order_by(EventAttentionSnapshot.window_end.desc())
        )
        values = {
            column.name: copy.deepcopy(getattr(row, column.name))
            for column in EventAttentionSnapshot.__table__.columns
        }
        values["id"] = uuid4()
        values["computed_at"] = now
        if bad == "permission":
            values["input_manifest"]["observation_ids"].append(str(uuid4()))
        values["input_fingerprint"] = (
            b"x" * 32
            if bad == "hash"
            else hashlib.sha256(
                json.dumps(values["input_manifest"], sort_keys=True, separators=(",", ":")).encode()
            ).digest()
        )
        session.add(EventAttentionSnapshot(**values))
    with sessions() as session:
        history = (
            PublicationApplicationService(session).home(owner_id=owner, now=now).stories[0].history
        )
        assert history.points[-1].value is None
        assert history.trend.reason == ("invalid" if bad == "hash" else "not_public")


@pytest.mark.parametrize(
    ("offset", "historical", "expected"),
    [(0, False, "recorded"), (1, False, "recomputed"), (0, True, "recomputed")],
)
def test_writer_kind_uses_utc_hour_and_explicit_historical_flag(
    editorial_client, offset, historical, expected
):
    owner, _, event, now = seed_history(editorial_client)
    sessions = editorial_client.app.state.session_factory
    at = now.replace(minute=0, second=0, microsecond=0)
    computed = (now + timedelta(hours=offset)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    with sessions.begin() as session:
        EventHeatService(session, clock=lambda: computed).refresh_in_transaction(
            owner_id=owner, event_id=event, at=at, historical=historical
        )
    with sessions.begin() as session:
        row = session.scalar(
            select(EventAttentionSnapshot)
            .where(
                EventAttentionSnapshot.event_id == event,
                EventAttentionSnapshot.formula_version == ATTENTION_FORMULA_VERSION,
                EventAttentionSnapshot.window_end == at,
            )
            .order_by(EventAttentionSnapshot.computed_at.desc())
        )
        assert row.input_manifest["measurement_kind"] == expected
