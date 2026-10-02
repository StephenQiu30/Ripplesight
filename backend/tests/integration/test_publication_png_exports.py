from collections.abc import Iterator
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text
from tests.integration.test_editorial_execution import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _run,
)
from tests.integration.test_editorial_execution import editorial_client as _editorial_client
from tests.integration.test_publication import _freeze_publication_clock

from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[TestClient]:
    _freeze_publication_clock(monkeypatch, request.module)
    yield from _editorial_client.__wrapped__()


def test_png_exports_check_live_permission_before_etag_and_never_purchase(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    content_id = run.content_id
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                license_name="受控分享许可",
                reason="PNG与撤回链路",
                release_delay_seconds=0,
            ),
        )
        published = service.publish_in_transaction(owner_id=owner, content_id=content_id, now=NOW)
        assert published
    urls = [f"/og/items/{content_id}.png", f"/og/posters/{content_id}.png"]
    etags = []
    with sessions() as session:
        before = session.scalar(text("SELECT count(*) FROM resource_usage_attempts"))
    for url, size in zip(urls, [(1200, 630), (1080, 1440)], strict=True):
        response = editorial_client.get(url)
        assert response.status_code == 200, (
            response.text[:100] if response.status_code != 200 else ""
        )
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        with Image.open(BytesIO(response.content)) as image:
            image.load()
            assert image.size == size
        etags.append(response.headers["etag"])
        cached = editorial_client.get(url, headers={"If-None-Match": etags[-1]})
        assert cached.status_code == 304 and not cached.content
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=content_id,
            now=NOW,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=published.revision,
                visibility="withdrawn",
                reason="撤回后旧ETag不得继续提供图片",
            ),
        )
    for url, etag in zip(urls, etags, strict=True):
        assert editorial_client.get(url, headers={"If-None-Match": etag}).status_code == 404
    with sessions() as session:
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == before


def test_static_png_is_offline_and_fixed_page_names_are_allowlisted(
    editorial_client: TestClient,
) -> None:
    for path in ("/og/site.png", "/og/pages/monthly.png", "/og/pages/codex-reset.png"):
        response = editorial_client.get(path)
        assert response.status_code == 200
        with Image.open(BytesIO(response.content)) as image:
            assert image.size == (1200, 630)
    assert editorial_client.get("/og/pages/admin.png").status_code == 422
    with editorial_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0
