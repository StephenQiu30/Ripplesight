from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, Response
from pydantic import ValidationError

from api.routers.source_capabilities import list_public_platforms
from connections.catalog import SOURCE_CATALOG, list_public_platform_catalog
from connections.catalog_schemas import PublicPlatformCapability, PublicPlatformEntryView


def test_research_catalog_is_complete_but_never_grants_execution() -> None:
    platforms = list_public_platform_catalog()
    assert {platform.platform_key for platform in platforms} == {
        "x",
        "instagram",
        "facebook",
        "threads",
        "douyin",
        "bilibili",
        "weibo",
    }
    entry_keys: set[str] = set()
    for platform in platforms:
        assert platform.inspected_revision == "0a3a66a1cb28a645ffe90577a68411886274a2ee"
        assert platform.entries
        for entry in platform.entries:
            assert entry.entry_key not in entry_keys
            entry_keys.add(entry.entry_key)
            assert entry.supplier_fee_cap_micros == 0
            assert not entry.execution_admitted
            assert not entry.trial_verified
            assert not entry.product_available
            assert entry.last_persisted_success_at is None
            assert entry.block_reason and entry.object_scope and entry.admission_requirements
            assert {item.capability for item in entry.capabilities} == set(PublicPlatformCapability)
            assert all(
                not item.execution_admitted
                and not item.trial_verified
                and not item.product_available
                for item in entry.capabilities
            )
            assert all(platform.inspected_revision in url for url in entry.evidence_urls)
    assert len(entry_keys) == 18
    # Candidate routes cannot become source presets through the managed registry.
    assert entry_keys.isdisjoint(entry.source_key for entry in SOURCE_CATALOG)


def test_query_scope_keeps_hotlist_tags_authors_and_unknown_separate() -> None:
    entries = {
        entry.entry_key: entry
        for platform in list_public_platform_catalog()
        for entry in platform.entries
    }
    assert entries["weibo.hot"].query_mode == "hotlist"
    assert entries["weibo.author"].query_mode == "author_feed"
    assert entries["weibo.keyword"].query_mode == "keyword_feed"
    assert entries["threads.search"].query_mode == "tag_feed"
    keyword = next(
        item
        for item in entries["threads.search"].capabilities
        if item.capability is PublicPlatformCapability.KEYWORD_SEARCH
    )
    assert keyword.documented_support == "unknown"
    assert entries["instagram.tags"].status == "excluded"
    assert entries["instagram.author"].status == "blocked"
    assert "共享 Cookie 缓存" in entries["instagram.author"].block_reason
    assert entries["instagram.private_api"].status == "excluded"
    assert entries["facebook.free_entry"].status == "missing"
    assert entries["facebook.free_entry"].route_template is None
    assert entries["x.author"].status == "blocked"
    assert entries["x.keyword"].fee_status == "disallowed"
    assert entries["douyin.author"].status == "blocked"
    assert entries["bilibili.author"].status == "blocked"
    assert entries["bilibili.keyword"].pagination.startswith("有限快照")


@pytest.mark.parametrize("field", ["execution_admitted", "trial_verified", "product_available"])
def test_research_dto_cannot_be_used_as_a_runtime_grant(field: str) -> None:
    payload = list_public_platform_catalog()[0].entries[0].model_dump()
    payload[field] = True
    with pytest.raises(ValidationError):
        PublicPlatformEntryView.model_validate(payload)


def test_catalog_read_has_no_external_io_or_shared_mutable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_external_client(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("catalog reads must not create an external client")

    monkeypatch.setattr(httpx, "Client", fail_external_client)
    monkeypatch.setattr(httpx, "AsyncClient", fail_external_client)
    response = Response()
    first = list_public_platforms(response, UUID(int=1))
    first.items.clear()
    second = list_public_platforms(Response(), UUID(int=2))
    assert len(second.items) == 7
    assert second.next_cursor is None
    assert response.headers["cache-control"] == "private, no-store"


def test_catalog_openapi_declares_authenticated_read_only_contract(app: FastAPI) -> None:
    endpoint = app.openapi()["paths"]["/api/source-capabilities/public-platforms"]
    assert set(endpoint) == {"get"}
    assert endpoint["get"]["operationId"] == "listPublicPlatformCatalog"
    assert endpoint["get"]["security"]
    assert "401" in endpoint["get"]["responses"]
    assert "PublicPlatformCatalogView" in app.openapi()["components"]["schemas"]
