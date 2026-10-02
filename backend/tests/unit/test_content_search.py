from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import content.services as content_services
from api.dependencies import get_content_service, get_demo_scope
from content.services import ContentService
from core.errors import ApplicationError


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (None, ()),
        ("\t \n", ()),
        ("  AGENT\t模型 Agent  ", ("agent", "模型")),
        ("model ai", ("ai", "model")),
        ("100% field_name C:\\models", ("100%", "c:\\models", "field_name")),
    ],
)
def test_search_terms_are_bounded_literal_and_canonical(
    query: str | None, expected: tuple[str, ...]
) -> None:
    assert content_services._content_search_terms(query) == expected


@pytest.mark.parametrize("query", ["a" * 201, "a b c d e f g", "ai\x00agent"])
def test_search_rejects_invalid_input_before_database_access(query: str) -> None:
    session = MagicMock()
    with pytest.raises(ApplicationError, match="invalid_content_filter"):
        ContentService(session).list_contents(owner_id=uuid4(), cursor=None, limit=20, q=query)
    session.rollback.assert_not_called()
    session.scalars.assert_not_called()


def test_content_search_is_documented_and_forwarded_without_runtime_dependencies(
    app: FastAPI,
) -> None:
    calls: list[dict[str, object]] = []
    owner_id = uuid4()

    def list_contents(**kwargs: object) -> tuple[list[object], None]:
        calls.append(kwargs)
        return [], None

    app.dependency_overrides[get_demo_scope] = lambda: owner_id
    app.dependency_overrides[get_content_service] = lambda: SimpleNamespace(
        list_contents=list_contents
    )
    client = TestClient(app)
    response = client.get("/api/contents", params={"q": "AI 模型", "source_key": "hackernews"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"items": [], "next_cursor": None}
    assert calls[0]["owner_id"] == owner_id
    assert calls[0]["q"] == "AI 模型"
    assert calls[0]["source_key"] == "hackernews"

    operation = app.openapi()["paths"]["/api/contents"]["get"]
    parameter = next(item for item in operation["parameters"] if item["name"] == "q")
    assert parameter["required"] is False
    assert parameter["schema"]["anyOf"][0]["maxLength"] == 200
    assert operation["operationId"] == "listContentRecords"
    assert "422" in operation["responses"]

    invalid = client.get("/api/contents", params={"q": "x" * 201})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"
    assert len(calls) == 1
