import base64
from collections.abc import Iterator
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
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

from core.errors import ApplicationError
from operations.site_schemas import SiteConfigurationInput
from operations.site_services import SiteConfigurationService
from publication.schemas import PublicationOverrideInput, SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[TestClient]:
    _freeze_publication_clock(monkeypatch, request.module)
    yield from _editorial_client.__wrapped__()


def test_contact_configuration_cas_replay_and_disabled_old_image(
    editorial_client: TestClient,
) -> None:
    settings = editorial_client.app.state.settings
    settings.operator_token = SecretStr("controlled-site-operator-token-32-bytes")
    headers = {
        "X-HotKey-Operator-Token": settings.operator_token.get_secret_value(),
        "X-HotKey-CSRF": "1",
    }
    assert editorial_client.get("/api/operations/site").status_code == 401
    public = editorial_client.get("/api/site/contact")
    assert public.status_code == 200 and public.json()["enabled"] is False
    assert public.json()["text"] is None
    assert public.headers["cache-control"] == "no-store"
    assert editorial_client.get("/api/site/meta").json()["robots_index"] is False
    settings.publication_indexing_enabled = True
    assert editorial_client.get("/api/site/meta").json()["robots_index"] is True
    settings.publication_indexing_enabled = False
    stream = BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    command = {
        "operation_id": str(uuid4()),
        "expected_revision": 0,
        "reason": "启用受控联系",
        "contact_enabled": True,
        "contact_title": "联系维护者",
        "contact_text": "受控反馈入口",
        "contact_url": "https://example.com/contact",
        "wechat_qr_action": "replace",
        "wechat_image": {
            "mime": "image/png",
            "data_base64": base64.b64encode(stream.getvalue()).decode(),
        },
    }
    saved = editorial_client.put("/api/operations/site", headers=headers, json=command)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert view["revision"] == 1
    image_url = view["wechat_qr_url"]
    image = editorial_client.get(image_url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    with Image.open(BytesIO(image.content)) as decoded:
        decoded.load()
        assert decoded.size == (32, 32)
    assert (
        editorial_client.put("/api/operations/site", headers=headers, json=command).json() == view
    )
    stale = {
        **command,
        "operation_id": str(uuid4()),
        "wechat_qr_action": "keep",
        "wechat_image": None,
    }
    assert (
        editorial_client.put("/api/operations/site", headers=headers, json=stale).status_code == 409
    )
    disable = {
        **stale,
        "operation_id": str(uuid4()),
        "expected_revision": 1,
        "contact_enabled": False,
    }
    assert (
        editorial_client.put("/api/operations/site", headers=headers, json=disable).status_code
        == 200
    )
    assert editorial_client.get(image_url).status_code == 404
    assert editorial_client.get("/api/site/contact").json()["text"] is None
    with editorial_client.app.state.session_factory() as session:
        assert session.scalar(text("SELECT count(*) FROM operations_audit_operations")) == 2
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == 0
        assert session.scalar(text("SELECT count(*) FROM ai_calls")) == 0


def test_contact_settings_owner_isolation_and_invalid_image_rollback(
    editorial_client: TestClient,
) -> None:
    sessions, settings = (
        editorial_client.app.state.session_factory,
        editorial_client.app.state.settings,
    )
    owner, other = uuid4(), uuid4()
    with sessions() as session:
        service = SiteConfigurationService(session, settings)
        command = SiteConfigurationInput(
            operation_id=uuid4(),
            expected_revision=0,
            reason="实际分区隔离",
            contact_enabled=True,
            contact_text="仅当前分区",
        )
        assert service.save(owner_id=owner, command=command).revision == 1
        assert not service.contact(owner_id=other).enabled
        with pytest.raises(ApplicationError, match="invalid_operations_input"):
            service.save(
                owner_id=owner,
                command=SiteConfigurationInput.model_validate(
                    {
                        **command.model_dump(mode="json"),
                        "operation_id": uuid4(),
                        "expected_revision": 1,
                        "wechat_qr_action": "replace",
                        "wechat_image": {"mime": "image/png", "data_base64": "AAAA"},
                    }
                ),
            )
        assert service.get(owner_id=owner).revision == 1


def test_two_qr_images_have_independent_replacement_and_shared_disable(
    editorial_client: TestClient,
) -> None:
    session_factory, settings = (
        editorial_client.app.state.session_factory,
        editorial_client.app.state.settings,
    )
    owner = uuid4()

    def image(color: str) -> dict[str, str]:
        stream = BytesIO()
        Image.new("RGB", (24, 24), color).save(stream, format="PNG")
        return {"mime": "image/png", "data_base64": base64.b64encode(stream.getvalue()).decode()}

    command = SiteConfigurationInput.model_validate(
        {
            "operation_id": uuid4(),
            "expected_revision": 0,
            "reason": "启用两个联系渠道",
            "contact_enabled": True,
            "contact_text": "公开联系",
            "wechat_qr_action": "replace",
            "wechat_image": image("black"),
            "feishu_qr_action": "replace",
            "feishu_image": image("white"),
        }
    )
    with session_factory() as session:
        service = SiteConfigurationService(session, settings)
        first = service.save(owner_id=owner, command=command)
        assert (
            first.wechat_qr_url
            and first.feishu_qr_url
            and first.wechat_qr_url != first.feishu_qr_url
        )
        old_wechat = first.wechat_qr_url.split("/")[-1].removesuffix(".png")
        feishu = first.feishu_qr_url.split("/")[-1].removesuffix(".png")
        assert service.image(owner_id=owner, sha256=feishu)
        revised = command.model_copy(
            update={
                "operation_id": uuid4(),
                "expected_revision": 1,
                "wechat_image": None,
                "wechat_qr_action": "clear",
                "feishu_image": None,
                "feishu_qr_action": "keep",
            }
        )
        value = service.save(owner_id=owner, command=revised)
        assert value.wechat_qr_url is None and value.feishu_qr_url == first.feishu_qr_url
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.image(owner_id=owner, sha256=old_wechat)
        assert service.image(owner_id=owner, sha256=feishu)
        service.save(
            owner_id=owner,
            command=revised.model_copy(
                update={"operation_id": uuid4(), "expected_revision": 2, "contact_enabled": False}
            ),
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.image(owner_id=owner, sha256=feishu)


def test_site_statistics_and_fallback_icon_recheck_public_release_and_withdrawal(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
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
                license_name="站点统计受控许可",
                reason="站点受控资料",
                release_delay_seconds=0,
            ),
        )
        published = service.publish_in_transaction(
            owner_id=owner, content_id=run.content_id, now=NOW
        )
        assert published
    stats = editorial_client.get("/api/site/stats")
    assert (
        stats.status_code == 200
        and stats.json()["visible_items"]
        == stats.json()["selected_items"]
        == stats.json()["visible_sources"]
        == 1
    )
    icon = editorial_client.get("/api/site/source-icons/x.svg")
    assert icon.status_code == 200 and icon.headers["content-type"].startswith("image/svg+xml")
    assert icon.headers["cache-control"] == "no-store"
    with sessions.begin() as session:
        PublicationService(session).override_in_transaction(
            owner_id=owner,
            actor_id=owner,
            content_id=run.content_id,
            now=NOW,
            command=PublicationOverrideInput(
                operation_id=uuid4(),
                expected_revision=published.revision,
                visibility="withdrawn",
                reason="当前许可撤回",
            ),
        )
        before = session.scalar(text("SELECT count(*) FROM resource_usage_attempts"))
    assert editorial_client.get("/api/site/stats").json()["visible_items"] == 0
    assert editorial_client.get("/api/site/source-icons/x.svg").status_code == 404
    with sessions() as session:
        assert session.scalar(text("SELECT count(*) FROM resource_usage_attempts")) == before
