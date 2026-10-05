"""Date admission and invalid JSON claims persist through the original editorial Job."""

import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.integration.test_editorial_source_profiles import NOW, begin, job, setup
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_sources import admitted_http

from connections.editorial_models import EditorialSourceMaterialReceipt, EditorialSourceProfile
from content.models import ContentObservation
from sources.editorial_registry import EditorialSourceRegistry
from sources.editorial_schemas import EditorialCursor


@pytest.mark.parametrize("kind", ["rss", "web_list", "json_list"])
def test_source_created_at_survives_delayed_first_import_and_persisted_cursor(kind, engine):
    options = {
        "rss": {"feed_url": "https://example.com/feed"},
        "web_list": {
            "url": "https://example.com/list",
            "item_selector": "article",
            "published_at_selector": "time",
        },
        "json_list": {
            "url": "https://example.com/list",
            "title_paths": ["title"],
            "url_template": "https://example.com/{id}",
            "published_at_path": "date",
        },
    }
    added = NOW - timedelta(days=10)
    dates = [added - timedelta(hours=48, seconds=1), added - timedelta(hours=48), None, added]
    if kind == "rss":
        listing = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            + "".join(
                f'<entry><title>Article {i}</title><link href="https://example.com/{i}"/>'
                + (f"<published>{date.isoformat()}</published>" if date else "")
                + "</entry>"
                for i, date in enumerate(dates)
            )
            + "</feed>"
        )
    elif kind == "web_list":
        listing = "".join(
            f'<article><a href="/{i}">Article {i}</a>'
            + (f'<time datetime="{date.isoformat()}"></time>' if date else "")
            + "</article>"
            for i, date in enumerate(dates)
        )
    else:
        listing = json.dumps(
            [
                {"id": i, "title": f"Article {i}", "date": date.isoformat() if date else None}
                for i, date in enumerate(dates)
            ]
        )
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = setup(
            session,
            kind=kind,
            configuration={
                **options[kind],
                "allowed_hosts": ["example.com"],
                "initial_backfill_limit": 2,
            },
        )
        with session.begin():
            session.get(EditorialSourceProfile, profile.id).created_at = added
        accepted, operation = job(session, owner, profile)
        prepared = begin(service, owner, profile, accepted, operation)
        assert prepared.source_added_at == added and prepared.cursor.initialized_at is None
        http, _ = admitted_http(lambda request: httpx.Response(200, text=listing))
        registry = EditorialSourceRegistry(
            http=http, clock=lambda: NOW, source_added_at=prepared.source_added_at
        )
        try:
            first = registry.collect(prepared.profile, prepared.cursor, prepared.known)
        finally:
            registry.close()
        assert first.status == "complete" and [m.title for m in first.materials] == [
            "Article 1",
            "Article 2",
        ]
        service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=first)
        assert service.apply_page(owner_id=owner, run_id=prepared.result.run_id).created == 2
        with session.begin():
            current = session.get(EditorialSourceProfile, profile.id)
            cursor = EditorialCursor.model_validate(current.cursor)
        assert cursor.initialized_at == NOW
        http, _ = admitted_http(lambda request: httpx.Response(200, text=listing))
        registry = EditorialSourceRegistry(
            http=http,
            clock=lambda: NOW + timedelta(days=1),
            source_added_at=prepared.source_added_at,
        )
        try:
            later = registry.collect(prepared.profile, cursor, {})
            assert later.status == "complete" and len(later.materials) == 4
        finally:
            registry.close()
        with session.begin():
            observations = list(session.scalars(select(ContentObservation)))
            assert len(observations) == 2
            assert {ob.published_at for ob in observations} == {dates[1], None}


def test_invalid_json_dates_keep_null_reason_and_following_material_in_database(engine):
    with Session(engine, expire_on_commit=False) as session:
        service, owner, profile, _ = setup(
            session,
            kind="json_list",
            configuration={
                "url": "https://example.com/list",
                "allowed_hosts": ["example.com"],
                "title_paths": ["title"],
                "url_template": "https://example.com/{id}",
                "published_at_path": "date",
            },
        )
        accepted, operation = job(session, owner, profile)
        prepared = begin(service, owner, profile, accepted, operation)
        values = [NOW.isoformat(), "invalid", {"toString": None}, NOW.isoformat()]
        listing = json.dumps(
            [{"id": i, "title": f"Article {i}", "date": value} for i, value in enumerate(values)]
        )
        http, _ = admitted_http(lambda request: httpx.Response(200, text=listing))
        registry = EditorialSourceRegistry(
            http=http, clock=lambda: NOW, source_added_at=prepared.source_added_at
        )
        try:
            page = registry.collect(prepared.profile, prepared.cursor, prepared.known)
        finally:
            registry.close()
        assert page.status == "complete" and len(page.materials) == 4
        service.stage_page(owner_id=owner, run_id=prepared.result.run_id, page=page)
        assert service.apply_page(owner_id=owner, run_id=prepared.result.run_id).created == 4
        with session.begin():
            observations = list(session.scalars(select(ContentObservation)))
            assert sum(ob.published_at is None for ob in observations) == 2
            receipts = list(session.scalars(select(EditorialSourceMaterialReceipt)))
            assert (
                sum(
                    r.material_metadata.get("publication_date_reason") == "invalid_publication_date"
                    for r in receipts
                )
                == 2
            )
