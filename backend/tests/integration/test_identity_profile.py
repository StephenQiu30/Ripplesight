import base64
import hashlib
from io import BytesIO

from PIL import Image
from tests.integration.test_identity_login import (
    create_account,
    login,
    write_headers,
)
from tests.integration.test_identity_login import (
    identity_app as identity_app,
)


def avatar_payload(color: str = "blue") -> dict[str, str]:
    output = BytesIO()
    Image.new("RGB", (80, 40), color).save(output, format="PNG")
    return {"mime": "image/png", "data_base64": base64.b64encode(output.getvalue()).decode()}


def test_avatar_persists_replaces_and_is_only_readable_by_its_owner(identity_app) -> None:
    app, client, _mail, _store = identity_app
    create_account(app, "avatar.first")
    create_account(app, "avatar.second")
    login(client, "avatar.first")
    assert client.put("/api/identity/avatar", json=avatar_payload()).status_code == 403
    uploaded = client.put(
        "/api/identity/avatar", json=avatar_payload(), headers=write_headers(client)
    )
    assert uploaded.status_code == 200, uploaded.text
    digest = uploaded.json()["user"]["avatar_sha256"]
    image = client.get("/api/identity/avatar", params={"sha256": digest})
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.headers["cache-control"] == "private, no-store"
    assert hashlib.sha256(image.content).hexdigest() == digest
    client.cookies.clear()
    assert client.get("/api/identity/avatar", params={"sha256": digest}).status_code == 401
    login(client, "avatar.second")
    assert client.get("/api/identity/avatar", params={"sha256": digest}).status_code == 404
    client.cookies.clear()
    login(client, "avatar.first")
    assert client.get("/api/identity/session").json()["user"]["avatar_sha256"] == digest
    replaced = client.put(
        "/api/identity/avatar", json=avatar_payload("red"), headers=write_headers(client)
    )
    assert replaced.json()["user"]["avatar_sha256"] != digest
    assert client.get("/api/identity/avatar", params={"sha256": digest}).status_code == 404
    rejected = client.put(
        "/api/identity/avatar",
        json={"mime": "image/png", "data_base64": "broken!"},
        headers=write_headers(client),
    )
    assert rejected.status_code == 422 and rejected.json()["code"] == "invalid_avatar"
    assert (
        client.get("/api/identity/session").json()["user"]["avatar_sha256"]
        == replaced.json()["user"]["avatar_sha256"]
    )


def test_username_can_change_without_password_or_session_rotation(identity_app) -> None:
    app, client, _mail, _store = identity_app
    create_account(app, "profile.owner")
    create_account(app, "profile.taken")
    login(client, "profile.owner")
    token = client.cookies.get("hotkey_session")
    assert client.put("/api/identity/profile", json={"username": "profile.new"}).status_code == 403
    response = client.put(
        "/api/identity/profile", json={"username": "Profile.New"}, headers=write_headers(client)
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["username"] == "profile.new"
    assert client.cookies.get("hotkey_session") == token
    assert client.get("/api/identity/session").json()["user"]["username"] == "profile.new"
    conflict = client.put(
        "/api/identity/profile", json={"username": "profile.taken"}, headers=write_headers(client)
    )
    assert conflict.status_code == 409
    assert client.get("/api/identity/session").json()["user"]["username"] == "profile.new"
    client.cookies.clear()
    assert login(client, "profile.new").status_code == 200
