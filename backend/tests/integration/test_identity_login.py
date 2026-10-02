from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import select, update

from core.config import Settings
from core.errors import ApplicationError
from identity.adapters.github import GitHubAdapter
from identity.adapters.verification_store import VerificationStore
from identity.models import IdentitySession, IdentityUser
from identity.services import IdentityService
from main import create_app

PASSWORD = "identity-test-password-123"


@dataclass
class RecordedEmail:
    codes: dict[str, str] = field(default_factory=dict)
    fail: bool = False

    def send_code(self, email: str, code: str) -> None:
        if self.fail:
            raise ApplicationError("email_delivery_unavailable")
        self.codes[email] = code


@pytest.fixture
def identity_app() -> Iterator[tuple[FastAPI, TestClient, RecordedEmail, VerificationStore]]:
    database = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if not database:
        pytest.skip("real isolated PostgreSQL is required")
    settings = Settings(
        _env_file=None,
        database_url=database,
        environment="test",
        redis_url=os.getenv("HOTKEY_TEST_REDIS_URL", "redis://127.0.0.1:6379/0"),
        auth_smtp_host="smtp.example.com",
        auth_smtp_from_email="identity@example.com",
        email_code_hmac_key="isolated-test-key-of-at-least-32-bytes",
        github_client_id="test-app",
        github_client_secret="test-secret",
    )
    application = create_app(settings)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    prefix = f"hotkey:test:identity:{uuid4().hex}:"
    store = VerificationStore(
        redis, settings.email_code_hmac_key.get_secret_value(), key_prefix=prefix
    )
    mail = RecordedEmail()
    application.state.identity_verification = store
    application.state.identity_email = mail
    with TestClient(application, base_url=settings.web_origin) as client:
        client.headers["Origin"] = settings.web_origin
        yield application, client, mail, store
    keys = list(redis.scan_iter(match=f"{prefix}*"))
    if keys:
        redis.unlink(*keys)
    redis.close()


def create_account(app: FastAPI, username: str, email: str | None = None) -> UUID:
    with app.state.session_factory() as session:
        return IdentityService(session, app.state.settings).create_account(
            username=username, password=PASSWORD, email=email
        )


def login(client: TestClient, username: str) -> httpx.Response:
    response = client.post(
        "/api/identity/sessions",
        headers={"X-HotKey-CSRF": "1"},
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response


def write_headers(client: TestClient) -> dict[str, str]:
    return {"X-HotKey-CSRF": client.cookies.get("hotkey_csrf")}


def test_password_session_cookie_digest_csrf_and_logout(identity_app) -> None:
    app, client, _mail, _store = identity_app
    owner = create_account(app, "owner.one")
    assert client.get("/api/topics").status_code == 401
    assert client.get("/feed.xml").status_code == 401
    assert client.get("/api/leaderboard/rules").status_code == 401
    response = login(client, "Owner.One")
    assert response.json()["user"] == {"id": str(owner), "username": "owner.one", "email": None}
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2 and "HttpOnly" in cookies[0] and "SameSite=lax" in cookies[0]
    assert "Max-Age=43200" in cookies[0] and "HttpOnly" not in cookies[1]
    assert client.get("/api/identity/session").json() == response.json()
    assert client.get("/api/topics").status_code == 200
    payload = {"name": "private topic", "match_any": ["AI"], "match_all": [], "exclude": []}
    assert (
        client.post("/api/topics", json=payload, headers={"X-HotKey-CSRF": "1"}).status_code == 403
    )
    created = client.post("/api/topics", json=payload, headers=write_headers(client))
    assert created.status_code == 201, created.text
    with app.state.session_factory() as session:
        rows = session.scalars(select(IdentitySession)).all()
        assert len(rows) == 1 and len(rows[0].token_digest) == 32
        assert client.cookies.get("hotkey_session").encode() != rows[0].token_digest
    token = client.cookies.get("hotkey_session")
    assert client.delete("/api/identity/session", headers=write_headers(client)).status_code == 204
    assert not client.cookies.get("hotkey_session")
    client.cookies.set("hotkey_session", token)
    assert client.get("/api/identity/session").status_code == 401


def test_two_real_accounts_cannot_read_or_mutate_each_others_topic(identity_app) -> None:
    app, client, _mail, _store = identity_app
    first, second = create_account(app, "first.user"), create_account(app, "second.user")
    assert first != second
    login(client, "first.user")
    response = client.post(
        "/api/topics",
        headers=write_headers(client),
        json={"name": "first only", "match_any": ["AI"], "match_all": [], "exclude": []},
    )
    assert response.status_code == 201, response.text
    location = response.headers["location"]
    client.cookies.clear()
    login(client, "second.user")
    assert client.get("/api/topics").json()["items"] == []
    assert client.get(location).status_code == 404
    assert client.post(location + "/pause", headers=write_headers(client)).status_code == 404


def test_login_origin_unknown_password_and_attempt_limit(identity_app) -> None:
    app, client, _mail, _store = identity_app
    create_account(app, "existing")
    payload = {"username": "existing", "password": PASSWORD}
    cross = client.post(
        "/api/identity/sessions",
        json=payload,
        headers={"Origin": "https://other.example", "X-HotKey-CSRF": "1"},
    )
    assert cross.status_code == 403 and not client.cookies
    for index in range(5):
        denied = client.post(
            "/api/identity/sessions",
            headers={"X-HotKey-CSRF": "1"},
            json={"username": "missing", "password": "a wrong and long password"},
        )
        assert denied.status_code == 401 and denied.json()["code"] == "invalid_credentials", index
    limited = client.post(
        "/api/identity/sessions",
        headers={"X-HotKey-CSRF": "1"},
        json={"username": "missing", "password": PASSWORD},
    )
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0


def test_email_real_redis_single_use_and_first_password_then_revocation(identity_app) -> None:
    _app, client, mail, _store = identity_app
    challenge = client.post(
        "/api/identity/email/challenges",
        headers={"X-HotKey-CSRF": "1"},
        json={"email": "New.User@example.com"},
    )
    assert challenge.status_code == 200, challenge.text
    assert "code" not in challenge.json()
    value = {
        "challenge_id": challenge.json()["challenge_id"],
        "code": mail.codes["new.user@example.com"],
    }
    result = client.post("/api/identity/email/sessions", headers={"X-HotKey-CSRF": "1"}, json=value)
    assert result.status_code == 200, result.text
    owner = UUID(result.json()["user"]["id"])
    assert client.get("/api/topics").json()["items"] == []
    assert (
        client.post(
            "/api/identity/email/sessions", headers={"X-HotKey-CSRF": "1"}, json=value
        ).status_code
        == 401
    )
    old_token = client.cookies.get("hotkey_session")
    updated = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={"username": "new.user", "password": PASSWORD},
    )
    assert updated.status_code == 204, updated.text
    assert not client.cookies.get("hotkey_session")
    client.cookies.set("hotkey_session", old_token)
    assert client.get("/api/identity/session").status_code == 401
    client.cookies.clear()
    assert UUID(login(client, "new.user").json()["user"]["id"]) == owner


def test_email_wrong_attempts_binding_cooldown_and_parallel_replay(identity_app) -> None:
    _app, _client, _mail, store = identity_app
    challenge = store.send_email_challenge("atomic@example.com", "10.0.0.1")
    with pytest.raises(ApplicationError, match="auth_rate_limited"):
        store.send_email_challenge("atomic@example.com", "10.0.0.1")
    wrong = "000000" if challenge.code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(ApplicationError, match="invalid_email_code"):
            store.consume_email_challenge(challenge.challenge_id, wrong, "10.0.0.2")
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        store.consume_email_challenge(challenge.challenge_id, challenge.code, "10.0.0.2")
    parallel = store.send_email_challenge("parallel@example.com", "10.0.0.1")

    def consume(_: int) -> str:
        try:
            return store.consume_email_challenge(parallel.challenge_id, parallel.code, "10.0.0.3")
        except ApplicationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(consume, range(8)))
    assert results.count("parallel@example.com") == 1
    assert results.count("invalid_email_code") == 7
    bound = store.send_email_challenge(
        "bound@example.com", "10.0.0.1", purpose="credentials_update", user_id="first"
    )
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        store.consume_email_challenge(
            bound.challenge_id,
            bound.code,
            "10.0.0.2",
            purpose="credentials_update",
            user_id="second",
        )
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        store.consume_email_challenge(bound.challenge_id, bound.code, "10.0.0.2")


def test_github_http_adapter_state_binding_and_email_links_same_user(identity_app) -> None:
    app, client, _mail, store = identity_app
    account = create_account(app, "linked.user", email="linked@example.com")

    def github(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            assert b"code_verifier=" in request.content
            return httpx.Response(
                200, json={"access_token": "temporary-test-token", "token_type": "bearer"}
            )
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 91234})
        return httpx.Response(
            200, json=[{"email": "linked@example.com", "primary": True, "verified": True}]
        )

    with httpx.Client(transport=httpx.MockTransport(github)) as http:
        app.state.identity_github = GitHubAdapter(
            http,
            "test-app",
            "test-secret",
            f"{app.state.settings.web_origin}/api/identity/github/callback",
        )
        response = client.post(
            "/api/identity/github/authorize",
            headers={"X-HotKey-CSRF": "1"},
            json={"return_to": "//bad.example"},
        )
        assert response.status_code == 200, response.text
        params = httpx.URL(response.json()["authorization_url"]).params
        assert params["code_challenge_method"] == "S256" and "scope" not in params
        state = params["state"]
        callback = client.get(
            "/api/identity/github/callback",
            params={"state": state, "code": "safe-code"},
            follow_redirects=False,
        )
        assert callback.status_code == 303 and callback.headers["location"] == "/topics"
        assert UUID(client.get("/api/identity/session").json()["user"]["id"]) == account
        repeated = client.get(
            "/api/identity/github/callback",
            params={"state": state, "code": "safe-code"},
            follow_redirects=False,
        )
        assert repeated.headers["location"] == "/login?error=invalid_oauth_state"
    flow = store.create_oauth_flow("/topics")
    with pytest.raises(ApplicationError, match="invalid_oauth_state"):
        store.consume_oauth_flow(flow.state, "wrong-binding")
    assert store.consume_oauth_flow(flow.state, flow.binding).return_to == "/topics"


def test_expiry_and_current_password_maintenance_revoke_all_sessions(identity_app) -> None:
    app, client, _mail, _store = identity_app
    owner = create_account(app, "maintained")
    login(client, "maintained")
    old = client.cookies.get("hotkey_session")
    response = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={"username": "maintained", "password": "another-password-123"},
    )
    assert response.status_code == 403
    changed = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={
            "username": "maintained",
            "password": "another-password-123",
            "current_password": PASSWORD,
        },
    )
    assert changed.status_code == 204, changed.text
    client.cookies.set("hotkey_session", old)
    assert client.get("/api/identity/session").status_code == 401

    with app.state.session_factory() as session, session.begin():
        session.execute(
            update(IdentityUser).where(IdentityUser.id == owner).values(credential_version=1)
        )
        session.execute(
            update(IdentitySession)
            .where(IdentitySession.user_id == owner)
            .values(
                revoked_at=None,
                revoked_reason=None,
                created_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
    assert client.get("/api/identity/session").status_code == 401


def test_smtp_failure_invalidates_challenge_and_does_not_create_account(identity_app) -> None:
    app, client, mail, store = identity_app
    mail.fail = True
    response = client.post(
        "/api/identity/email/challenges",
        headers={"X-HotKey-CSRF": "1"},
        json={"email": "failed@example.com"},
    )
    assert response.status_code == 503 and response.json()["code"] == "email_delivery_unavailable"
    assert not client.cookies
    assert list(store._redis.scan_iter(match=f"{store._prefix}email-challenge:*")) == []
    with app.state.session_factory() as session:
        assert session.scalars(select(IdentityUser)).all() == []


def test_credential_email_verification_is_bound_to_the_authenticated_account(identity_app) -> None:
    app, client, mail, _store = identity_app
    create_account(app, "email.maintained", email="maintained@example.com")
    login(client, "email.maintained")
    mismatch = client.post(
        "/api/identity/email/challenges",
        headers=write_headers(client),
        json={"email": "different@example.com"},
    )
    assert mismatch.status_code == 401
    challenge = client.post(
        "/api/identity/email/challenges",
        headers=write_headers(client),
        json={"email": "maintained@example.com"},
    )
    assert challenge.status_code == 200, challenge.text
    value = {
        "challenge_id": challenge.json()["challenge_id"],
        "code": mail.codes["maintained@example.com"],
    }
    assert (
        client.post(
            "/api/identity/email/sessions", headers={"X-HotKey-CSRF": "1"}, json=value
        ).status_code
        == 401
    )
    updated = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={"username": "email.maintained", "password": "replacement-password-123", **value},
    )
    assert updated.status_code == 204, updated.text


def test_email_hmac_prevents_a_redis_address_change_from_logging_in_someone_else(
    identity_app,
) -> None:
    _app, _client, _mail, store = identity_app
    challenge = store.send_email_challenge("straße@example.com", "10.0.0.1")
    key = store._key("email-challenge", challenge.challenge_id)
    assert store._redis.hget(key, "email") == "straße@example.com".encode()
    store._redis.hset(key, "email", "strasse@example.com")
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        store.consume_email_challenge(challenge.challenge_id, challenge.code, "10.0.0.1")


def test_redis_unavailable_rejects_password_login(identity_app) -> None:
    app, client, _mail, _store = identity_app
    create_account(app, "redis.user")
    broken = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.1, socket_timeout=0.1)
    app.state.identity_verification = VerificationStore(broken, None)
    try:
        response = client.post(
            "/api/identity/sessions",
            headers={"X-HotKey-CSRF": "1"},
            json={"username": "redis.user", "password": PASSWORD},
        )
        assert (
            response.status_code == 503 and response.json()["code"] == "auth_dependency_unavailable"
        )
        assert not client.cookies
    finally:
        broken.close()


def test_expired_session_does_not_block_a_new_anonymous_email_login(identity_app) -> None:
    app, client, mail, _store = identity_app
    create_account(app, "stale.user")
    login(client, "stale.user")
    token = client.cookies.get("hotkey_session")
    assert client.delete("/api/identity/session", headers=write_headers(client)).status_code == 204
    client.cookies.set("hotkey_session", token)
    challenge = client.post(
        "/api/identity/email/challenges",
        headers={"X-HotKey-CSRF": "1"},
        json={"email": "fresh@example.com"},
    )
    assert challenge.status_code == 200, challenge.text
    assert any("Max-Age=0" in cookie for cookie in challenge.headers.get_list("set-cookie"))
    verified = client.post(
        "/api/identity/email/sessions",
        headers={"X-HotKey-CSRF": "1"},
        json={
            "challenge_id": challenge.json()["challenge_id"],
            "code": mail.codes["fresh@example.com"],
        },
    )
    assert verified.status_code == 200
