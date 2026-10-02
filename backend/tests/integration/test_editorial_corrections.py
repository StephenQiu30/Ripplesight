from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from tests.integration.test_editorial_execution import (
    ControlledClient,
    _budget,
    _execute,
    _run,
)
from tests.integration.test_editorial_execution import editorial_client as _editorial_client
from tests.integration.test_publication import _freeze_publication_clock


@pytest.fixture
def editorial_client(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[TestClient]:
    _freeze_publication_clock(monkeypatch, request.module)
    yield from _editorial_client.__wrapped__()


def test_partial_human_fields_clear_to_original_automatic_evidence_without_new_ai(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    settings = editorial_client.app.state.settings
    settings.operator_token = SecretStr("controlled-editorial-operator-token-32-bytes")
    headers = {
        "X-HotKey-Operator-Token": settings.operator_token.get_secret_value(),
        "X-HotKey-CSRF": editorial_client.cookies["hotkey_csrf"],
    }
    path = f"/api/editorial/runs/{run.id}/corrections"
    original = editorial_client.get(f"/api/editorial/runs/{run.id}").json()
    assert original["result"]["selected"] is True
    command = {
        "operation_id": str(uuid4()),
        "expected_manual_version": 0,
        "selected": False,
        "silent": True,
        "tags": ["模型"],
        "reason": "暂不推送但保留自动中文文案",
    }
    assert editorial_client.post(path, json=command).status_code == 401
    assert (
        editorial_client.post(
            path,
            headers={"X-HotKey-Operator-Token": settings.operator_token.get_secret_value()},
            json=command,
        ).status_code
        == 403
    )
    saved = editorial_client.post(path, headers=headers, json=command)
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["manual_version"] == 1
    assert data["result"]["silent"] is True and data["result"]["selected"] is False
    assert data["result"]["writing"] == original["result"]["writing"]
    assert data["result"]["tags_override"] == ["模型发布"]
    assert editorial_client.post(path, headers=headers, json=command).json() == data
    stale = {**command, "operation_id": str(uuid4())}
    assert editorial_client.post(path, headers=headers, json=stale).status_code == 409
    partial = editorial_client.post(
        path,
        headers=headers,
        json={
            "operation_id": str(uuid4()),
            "expected_manual_version": 1,
            "clear_fields": ["silent"],
            "reason": "只恢复推送",
        },
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["result"]["silent"] is False
    assert partial.json()["result"]["selected"] is False
    cleared = editorial_client.post(
        path,
        headers=headers,
        json={
            "operation_id": str(uuid4()),
            "expected_manual_version": 2,
            "action": "clear",
            "reason": "全部恢复自动结果",
        },
    )
    assert cleared.status_code == 200, cleared.text
    result = cleared.json()["result"]
    assert cleared.json()["manual_version"] == 3 and result["manual"] is False
    assert result["selected"] == original["result"]["selected"]
    assert result["writing"] == original["result"]["writing"]
    assert result["tags_override"] is None and result["manual_overrides"] == {}
    # A late replay returns its original receipt without replacing the newer cleared result.
    assert editorial_client.post(path, headers=headers, json=command).json() == data
    current = editorial_client.get(f"/api/editorial/runs/{run.id}").json()
    assert current["manual_version"] == 3 and current["result"]["manual"] is False
    with editorial_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM editorial_overrides")) == 3
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 5
        assert (
            session.scalar(text("SELECT count(*) FROM editorial_stages WHERE status='succeeded'"))
            == 5
        )
    with editorial_client.app.state.session_factory.begin() as session:
        session.execute(text("UPDATE evidence_resources SET expires_at=collected_at"))
    assert editorial_client.post(path, headers=headers, json=command).status_code == 404
    assert (
        editorial_client.get(
            f"/api/editorial/contents/{run.content_id}", headers=headers
        ).status_code
        == 404
    )


def test_clear_command_cannot_hide_simultaneous_replacements(editorial_client: TestClient) -> None:
    _owner, run, _message, _lease = _run(editorial_client)
    settings = editorial_client.app.state.settings
    settings.operator_token = SecretStr("controlled-editorial-operator-token-32-bytes")
    headers = {
        "X-HotKey-Operator-Token": settings.operator_token.get_secret_value(),
        "X-HotKey-CSRF": editorial_client.cookies["hotkey_csrf"],
    }
    response = editorial_client.post(
        f"/api/editorial/runs/{run.id}/corrections",
        headers=headers,
        json={
            "operation_id": str(uuid4()),
            "expected_manual_version": 0,
            "action": "clear",
            "silent": False,
            "reason": "无效的互斥命令",
        },
    )
    assert response.status_code == 422
    with editorial_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM editorial_overrides")) == 0
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0


def test_operator_rerun_preserves_fixed_content_and_queue_and_rejects_anonymous_writes(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    settings = editorial_client.app.state.settings
    settings.operator_token = SecretStr("controlled-editorial-operator-token-32-bytes")
    headers = {
        "X-HotKey-Operator-Token": settings.operator_token.get_secret_value(),
        "X-HotKey-CSRF": editorial_client.cookies["hotkey_csrf"],
    }
    corrected = editorial_client.post(
        f"/api/editorial/runs/{run.id}/corrections",
        headers=headers,
        json={
            "operation_id": str(uuid4()),
            "expected_manual_version": 0,
            "category": "paper",
            "reason_zh": "公开推荐理由",
            "reason": "私有审计",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["result"]["structure"]["category"] == "paper"
    assert corrected.json()["result"]["writing"]["reason_zh"] == "公开推荐理由"
    path = f"/api/editorial/contents/{run.content_id}/runs?source_key=x"
    command = {
        "operation_id": str(uuid4()),
        "content_version_id": str(run.content_version_id),
        "expected_manual_version": 1,
        "stages": "all",
    }
    assert (
        editorial_client.post(
            path, headers={"X-HotKey-CSRF": editorial_client.cookies["hotkey_csrf"]}, json=command
        ).status_code
        == 401
    )
    assert (
        editorial_client.post(
            path,
            headers={"X-HotKey-Operator-Token": settings.operator_token.get_secret_value()},
            json=command,
        ).status_code
        == 403
    )
    queued = editorial_client.post(path, headers=headers, json=command)
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "queued" and queued.json()["result"] is None
    assert queued.json()["content_version_id"] == str(run.content_version_id)
    assert queued.json()["manual_version"] == 1 and queued.json()["job_id"] != str(run.job_id)
    assert editorial_client.post(path, headers=headers, json=command).json() == queued.json()
    with editorial_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 5
        assert session.scalar(text("SELECT count(*) FROM editorial_runs")) == 2
        assert (
            session.scalar(
                text("SELECT count(*) FROM outbox_messages WHERE aggregate_id=:job"),
                {"job": queued.json()["job_id"]},
            )
            == 1
        )
    assert (
        editorial_client.put(
            "/api/editorial/sources/x",
            headers={"X-HotKey-CSRF": editorial_client.cookies["hotkey_csrf"]},
            json={
                "operation_id": str(uuid4()),
                "expected_revision": 1,
                "tier": "T1",
                "source_kind": "x_search",
                "name": "操作员来源",
                "enabled": True,
            },
        ).status_code
        == 401
    )
