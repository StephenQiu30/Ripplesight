import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_identity_service
from core.config import Settings
from core.errors import ApplicationError
from knowledge.document_services import WorkspaceDocumentService
from main import create_app

OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
SNAPSHOT = "a" * 64


@pytest.fixture
def document_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/hotkey_test_workspace_unit",
        workspace_document_tool_root=tmp_path / "tools",
        workspace_document_source_root=tmp_path / "source",
        workspace_document_snapshot_root=tmp_path / "store",
        workspace_document_read_user_ids=(OWNER,),
        workspace_document_write_user_ids=(OWNER,),
        workspace_document_publish_user_ids=(OWNER,),
    )


def test_authorization_precedes_filesystem_and_command(
    document_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def prohibited(*args: Any, **kwargs: Any) -> None:
        pytest.fail("unauthorized command reached the document tool")

    monkeypatch.setattr("knowledge.document_services.subprocess.run", prohibited)
    service = WorkspaceDocumentService(document_settings)
    for action in ("list", "read", "search", "raw", "attachment", "draft", "history", "operation"):
        with pytest.raises(ApplicationError, match="workspace_forbidden"):
            service.execute(OTHER, action)
    document_settings.workspace_document_write_user_ids = ()
    for action in ("save", "publish", "sync", "restore", "replace"):
        with pytest.raises(ApplicationError, match="workspace_forbidden"):
            service.execute(OWNER, action)


def test_active_checkout_and_missing_configuration_do_not_fall_back(
    document_settings: Settings,
) -> None:
    document_settings.workspace_document_source_root = (
        document_settings.workspace_document_tool_root.parent
    )
    with pytest.raises(ApplicationError, match="workspace_unavailable"):
        WorkspaceDocumentService(document_settings).execute(OWNER, "list")
    document_settings.workspace_document_tool_root = None
    with pytest.raises(ApplicationError, match="workspace_unavailable"):
        WorkspaceDocumentService(document_settings).execute(OWNER, "list")


def test_all_document_http_outlets_require_identity_and_no_store(
    document_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def command(*args: Any, **kwargs: Any) -> CompletedProcess[str]:
        data = json.loads(kwargs["input"])
        calls.append(data)
        action = data["action"]
        result: dict[str, Any] = {
            "list": {"snapshot_id": SNAPSHOT, "source_revision": "fixture", "documents": []},
            "raw": {"markdown": "# 原文\n", "snapshot_id": SNAPSHOT, "source_hash": "b" * 64},
            "attachment": {"body": "5paH5qGj", "mime": "text/plain"},
            "search": {"snapshot_id": SNAPSHOT, "items": []},
            "history": {"items": []},
            "operation": {"status": "pending", "operation_id": str(OWNER)},
        }.get(action, {})
        return CompletedProcess(args, 0, json.dumps({"result": result}), "")

    class ControlledIdentity:
        def authenticate(self, token: str | None) -> Any:
            if token not in {"owner", "other"}:
                raise ApplicationError("invalid_session")
            return SimpleNamespace(
                view=SimpleNamespace(
                    user=SimpleNamespace(id=OWNER if token == "owner" else OTHER, has_password=True)
                )
            )

        def validate_csrf(self, identity: Any, *, cookie: str | None, header: str | None) -> None:
            if cookie != "fixture-csrf" or header != cookie:
                raise ApplicationError("csrf_invalid")

    monkeypatch.setattr("knowledge.document_services.subprocess.run", command)
    app = create_app(document_settings)
    app.dependency_overrides[get_identity_service] = ControlledIdentity
    with TestClient(app) as client:
        endpoints = [
            "",
            "/document?path=index.md",
            "/search?query=权限",
            "/raw?path=index.md",
            f"/attachment?attachment_id={'b' * 64}",
            "/draft?path=index.md",
            "/history?path=index.md",
            f"/operations/{OWNER}",
        ]
        for suffix in endpoints:
            response = client.get("/api/workspace/documents" + suffix)
            assert response.status_code == 401
            assert response.headers["cache-control"] == "private, no-store"
        client.cookies.set("hotkey_session", "other")
        for suffix in endpoints:
            response = client.get("/api/workspace/documents" + suffix)
            assert response.status_code == 403
            assert response.headers["cache-control"] == "private, no-store"
        assert calls == []
        client.cookies.set("hotkey_session", "owner")
        for suffix in (
            "",
            "/search?query=权限",
            "/raw?path=index.md",
            f"/attachment?attachment_id={'b' * 64}",
            "/history?path=index.md",
            f"/operations/{OWNER}",
        ):
            response = client.get("/api/workspace/documents" + suffix)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store"
        assert all(item["owner_id"] == str(OWNER) for item in calls)
        for url, body, method in (
            (
                "/draft",
                {
                    "path": "index.md",
                    "snapshot_id": SNAPSHOT,
                    "source_hash": "b" * 64,
                    "draft_revision": 0,
                    "operation_id": str(OWNER),
                    "markdown": "\n保持空白\n",
                },
                "PUT",
            ),
            (
                "/publish",
                {
                    "path": "index.md",
                    "snapshot_id": SNAPSHOT,
                    "source_hash": "b" * 64,
                    "draft_revision": 0,
                    "operation_id": str(OWNER),
                },
                "POST",
            ),
        ):
            previous = len(calls)
            response = client.request(method, "/api/workspace/documents" + url, json=body)
            assert response.status_code == 403
            assert len(calls) == previous
            client.cookies.set("hotkey_csrf", "fixture-csrf")
            response = client.request(
                method,
                "/api/workspace/documents" + url,
                json=body,
                headers={"Origin": "https://different.example", "X-HotKey-CSRF": "fixture-csrf"},
            )
            assert response.status_code == 403
            assert len(calls) == previous
