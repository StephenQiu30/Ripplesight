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
from identity.email_challenges import EmailChallenges
from identity.models import IdentityEmailChallenge, IdentitySession, IdentityUser
from identity.schemas import IdentityCredentialsUpdateInput
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
    assert client.get("/api/leaderboard/rules").status_code == 200
    response = login(client, "Owner.One")
    assert response.json()["user"] == {
        "id": str(owner),
        "username": "owner.one",
        "email": None,
        "has_password": True,
        "github_connected": False,
        "avatar_sha256": None,
    }
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
    app, client, mail, _store = identity_app
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
    assert result.json()["user"]["email"] == "new.user@example.com"
    assert result.json()["user"]["has_password"] is False
    for path in ("/api/topics", "/api/contents", "/api/source-capabilities"):
        incomplete = client.get(path)
        assert incomplete.status_code == 403
        assert incomplete.json()["code"] == "account_setup_required"
    incomplete_write = client.post(
        "/api/topics",
        headers=write_headers(client),
        json={"name": "premature", "match_any": ["AI"], "match_all": [], "exclude": []},
    )
    assert incomplete_write.status_code == 403
    assert incomplete_write.json()["code"] == "account_setup_required"
    assert (
        client.post(
            "/api/identity/email/sessions", headers={"X-HotKey-CSRF": "1"}, json=value
        ).status_code
        == 401
    )
    old_token = client.cookies.get("hotkey_session")
    old_csrf = client.cookies.get("hotkey_csrf")
    no_password = client.post(
        "/api/identity/sessions",
        headers={"X-HotKey-CSRF": "1"},
        json={"username": "new.user@example.com", "password": PASSWORD},
    )
    assert no_password.status_code == 401 and no_password.json()["code"] == "invalid_credentials"
    updated = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={"username": "new.user", "password": PASSWORD},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["user"] == {
        "id": str(owner),
        "username": "new.user",
        "email": "new.user@example.com",
        "has_password": True,
        "github_connected": False,
        "avatar_sha256": None,
    }
    assert updated.headers["cache-control"] == "no-store"
    assert client.cookies.get("hotkey_session") != old_token
    assert client.cookies.get("hotkey_csrf") != old_csrf
    assert client.get("/api/identity/session").json() == updated.json()
    assert (
        client.get(
            "/api/identity/session", headers={"Cookie": f"hotkey_session={old_token}"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/topics",
            headers={"X-HotKey-CSRF": old_csrf},
            json={"name": "stale csrf", "match_any": ["AI"], "match_all": [], "exclude": []},
        ).status_code
        == 403
    )
    with app.state.session_factory() as session:
        user = session.get(IdentityUser, owner)
        assert user.password_hash is not None and user.password_hash != PASSWORD
        assert user.credential_version == 2
        rows = session.scalars(
            select(IdentitySession).where(IdentitySession.user_id == owner)
        ).all()
        assert len(rows) == 2
        assert sum(row.revoked_reason == "password_changed" for row in rows) == 1
        assert sum(row.revoked_at is None and row.credential_version == 2 for row in rows) == 1
    client.cookies.clear()
    assert UUID(login(client, "new.user").json()["user"]["id"]) == owner
    client.cookies.clear()
    assert UUID(login(client, " New.User@Example.COM ").json()["user"]["id"]) == owner


def test_email_password_login_accepts_long_email_and_preserves_uniform_denials(
    identity_app,
) -> None:
    app, client, _mail, _store = identity_app
    email = "account@" + "a" * 63 + ".example.com"
    owner = create_account(app, "long.email.user", email=email)
    assert UUID(login(client, email).json()["user"]["id"]) == owner
    client.cookies.clear()
    for identifier, password in (
        ("long.email.user", "a wrong and long password"),
        (email, "a wrong and long password"),
        ("missing.user", PASSWORD),
        ("missing@example.com", PASSWORD),
    ):
        denied = client.post(
            "/api/identity/sessions",
            headers={"X-HotKey-CSRF": "1"},
            json={"username": identifier, "password": password},
        )
        assert denied.status_code == 401 and denied.json()["code"] == "invalid_credentials"
        assert not client.cookies.get("hotkey_session")


def test_first_password_requires_fresh_database_session_or_bound_email_verification(
    identity_app,
) -> None:
    app, client, mail, store = identity_app
    email = "stale.first@example.com"
    with app.state.session_factory() as session:
        created = IdentityService(session, app.state.settings)._verified_login(
            email=email, github_user_id=None
        )
        stale_identity = IdentityService(session, app.state.settings).authenticate(
            created.session_token
        )
    client.cookies.set("hotkey_session", created.session_token)
    client.cookies.set("hotkey_csrf", created.csrf_token)
    with app.state.session_factory() as session, session.begin():
        session.execute(
            update(IdentitySession)
            .where(IdentitySession.user_id == created.view.user.id)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=6))
        )
    command = IdentityCredentialsUpdateInput(username="stale.first", password=PASSWORD)
    with (
        app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="credentials_verification_required"),
    ):
        IdentityService(session, app.state.settings, verification=store).update_credentials(
            identity=stale_identity, command=command, client_ip="127.0.0.1"
        )
    denied = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json=command.model_dump(mode="json") | {"password": PASSWORD},
    )
    assert denied.status_code == 403
    assert client.get("/api/identity/session").json()["user"]["has_password"] is False
    challenge = client.post(
        "/api/identity/email/challenges", headers=write_headers(client), json={"email": email}
    )
    assert challenge.status_code == 200, challenge.text
    updated = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={
            "username": "stale.first",
            "password": PASSWORD,
            "challenge_id": challenge.json()["challenge_id"],
            "code": mail.codes[email],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["user"]["has_password"] is True
    assert client.get("/api/identity/session").json() == updated.json()


def test_first_password_conflicting_username_rolls_back_hash_version_and_session(
    identity_app,
) -> None:
    app, client, _mail, _store = identity_app
    create_account(app, "claimed.username")
    with app.state.session_factory() as session:
        created = IdentityService(session, app.state.settings)._verified_login(
            email="conflict@example.com", github_user_id=None
        )
    client.cookies.set("hotkey_session", created.session_token)
    client.cookies.set("hotkey_csrf", created.csrf_token)
    conflict = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={"username": "claimed.username", "password": PASSWORD},
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "username_unavailable"
    assert client.cookies.get("hotkey_session") == created.session_token
    assert client.get("/api/identity/session").json()["user"]["has_password"] is False
    with app.state.session_factory() as session:
        user = session.get(IdentityUser, created.view.user.id)
        assert user.password_hash is None and user.credential_version == 1
        rows = session.scalars(
            select(IdentitySession).where(IdentitySession.user_id == user.id)
        ).all()
        assert len(rows) == 1 and rows[0].revoked_at is None


@pytest.mark.parametrize(
    "change", ["ownership", "revoked", "expired", "credential_version", "user_version"]
)
def test_password_setup_rechecks_current_session_in_database(identity_app, change: str) -> None:
    app, _client, _mail, store = identity_app
    other = create_account(app, "other.account")
    with app.state.session_factory() as session:
        created = IdentityService(session, app.state.settings)._verified_login(
            email="recheck@example.com", github_user_id=None
        )
        identity = IdentityService(session, app.state.settings).authenticate(created.session_token)
    changes = {
        "ownership": {"user_id": other},
        "revoked": {"revoked_at": datetime.now(UTC), "revoked_reason": "logout"},
        "expired": {
            "created_at": datetime.now(UTC) - timedelta(hours=2),
            "expires_at": datetime.now(UTC) - timedelta(hours=1),
        },
        "credential_version": {"credential_version": 2},
    }
    with app.state.session_factory() as session, session.begin():
        if change == "user_version":
            session.execute(
                update(IdentityUser)
                .where(IdentityUser.id == created.view.user.id)
                .values(credential_version=2)
            )
        else:
            session.execute(
                update(IdentitySession)
                .where(IdentitySession.id == identity.session_id)
                .values(**changes[change])
            )
    with (
        app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="invalid_session"),
    ):
        IdentityService(session, app.state.settings, verification=store).update_credentials(
            identity=identity,
            command=IdentityCredentialsUpdateInput(username="recheck", password=PASSWORD),
            client_ip="127.0.0.1",
        )
    with app.state.session_factory() as session:
        user = session.get(IdentityUser, created.view.user.id)
        assert user.password_hash is None
        assert user.credential_version == (2 if change == "user_version" else 1)


NONCE = "b" * 43


def issue_email(app, store, email, purpose="login", binding=None):
    with app.state.session_factory() as session:
        domain = EmailChallenges(session, store)
        return domain.issue(email, "10.0.0.1", purpose, binding or domain.browser_binding(NONCE))


def redeem_email(app, store, challenge, code=None, nonce=NONCE):
    with app.state.session_factory() as session:
        return IdentityService(session, app.state.settings, verification=store).verify_email(
            challenge_id=UUID(challenge.challenge_id),
            code=code or challenge.code,
            client_ip="10.0.0.2",
            browser_binding=nonce,
        )


def test_email_wrong_attempts_binding_cooldown_and_parallel_replay(identity_app) -> None:
    app, _client, _mail, store = identity_app
    challenge = issue_email(app, store, "atomic@example.com")
    with pytest.raises(ApplicationError, match="auth_rate_limited"):
        issue_email(app, store, "atomic@example.com")
    wrong = "000000" if challenge.code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(ApplicationError, match="invalid_email_code"):
            redeem_email(app, store, challenge, wrong)
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        redeem_email(app, store, challenge)
    with app.state.session_factory() as session:
        assert session.scalar(select(IdentityEmailChallenge)).attempt_count == 5
        assert session.scalars(select(IdentityUser)).all() == []
    parallel = issue_email(app, store, "parallel@example.com")

    def consume(_: int) -> str:
        try:
            return redeem_email(app, store, parallel).view.user.email
        except ApplicationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(consume, range(8)))
    assert results.count("parallel@example.com") == 1
    assert results.count("invalid_email_code") == 7
    bound = issue_email(app, store, "bound@example.com", "credentials_update")
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        redeem_email(app, store, bound)


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
        assert params["code_challenge_method"] == "S256"
        assert params["scope"] == "user:email"
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
    login(client, "maintained")
    other_old = client.cookies.get("hotkey_session")
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
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["has_password"] is True
    assert client.cookies.get("hotkey_session") not in {old, other_old}
    assert client.get("/api/identity/session").json() == changed.json()
    for token in (old, other_old):
        assert (
            client.get(
                "/api/identity/session", headers={"Cookie": f"hotkey_session={token}"}
            ).status_code
            == 401
        )

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
        row = session.scalar(select(IdentityEmailChallenge))
        assert row.invalidated_at is not None and row.consumed_at is None


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
    assert updated.status_code == 200, updated.text
    assert updated.json()["user"]["has_password"] is True
    assert client.get("/api/identity/session").json() == updated.json()


def test_email_hmac_prevents_a_database_address_change_from_logging_in_someone_else(
    identity_app,
) -> None:
    app, _client, _mail, store = identity_app
    challenge = issue_email(app, store, "straße@example.com")
    with app.state.session_factory() as session, session.begin():
        row = session.scalar(select(IdentityEmailChallenge))
        assert row.email == "straße@example.com"
        row.email = "strasse@example.com"
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        redeem_email(app, store, challenge)
    with app.state.session_factory() as session:
        assert session.scalars(select(IdentityUser)).all() == []


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


def link_code(client: TestClient, mail: RecordedEmail, email: str) -> dict[str, str]:
    response = client.post(
        "/api/identity/email/link/challenges", headers=write_headers(client), json={"email": email}
    )
    assert response.status_code == 200, response.text
    return {"challenge_id": response.json()["challenge_id"], "code": mail.codes[email]}


def test_github_account_binds_new_email_without_changing_owner_or_provider(identity_app) -> None:
    app, client, mail, _store = identity_app
    with app.state.session_factory() as session:
        created = IdentityService(session, app.state.settings)._verified_login(
            email="github.primary@example.com", github_user_id="12345"
        )
    client.cookies.set("hotkey_session", created.session_token, domain="127.0.0.1")
    client.cookies.set("hotkey_csrf", created.csrf_token, domain="127.0.0.1")
    payload = link_code(client, mail, "login.mail@example.com")
    # A binding proof is not a login proof, even on the same browser.
    rejected = client.post(
        "/api/identity/email/sessions", json=payload, headers={"X-HotKey-CSRF": "1"}
    )
    assert rejected.status_code == 401
    changed = client.put("/api/identity/email/link", headers=write_headers(client), json=payload)
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["id"] == str(created.view.user.id)
    assert changed.json()["user"]["github_connected"] is True
    assert changed.json()["user"]["email"] == "login.mail@example.com"
    assert client.cookies["hotkey_session"] != created.session_token
    assert (
        client.get(
            "/api/identity/session", headers={"Cookie": f"hotkey_session={created.session_token}"}
        ).status_code
        == 401
    )
    assert (
        client.put(
            "/api/identity/email/link", headers=write_headers(client), json=payload
        ).status_code
        == 401
    )
    with app.state.session_factory() as session:
        user = session.get(IdentityUser, created.view.user.id)
        assert user.github_user_id == "12345"
        assert user.credential_version == 2
        rows = session.scalars(select(IdentityUser)).all()
        assert len(rows) == 1
        # GitHub login continues to find the same account after the login email changed.
    with app.state.session_factory() as session:
        github_login = IdentityService(session, app.state.settings)._verified_login(
            email="github.primary@example.com", github_user_id="12345"
        )
        assert github_login.view.user.id == created.view.user.id
        assert github_login.view.user.email == "login.mail@example.com"


def test_email_link_rejects_other_owner_and_preserves_current_session(identity_app) -> None:
    app, client, mail, _store = identity_app
    owner = create_account(app, "link.owner", "owner@example.com")
    other = create_account(app, "link.other", "taken@example.com")
    login(client, "link.owner")
    original = client.cookies["hotkey_session"]
    payload = link_code(client, mail, "taken@example.com")
    changed = client.put("/api/identity/email/link", headers=write_headers(client), json=payload)
    assert changed.status_code == 409 and changed.json()["code"] == "identity_link_conflict"
    assert client.cookies["hotkey_session"] == original
    assert client.get("/api/identity/session").json()["user"]["id"] == str(owner)
    with app.state.session_factory() as session:
        assert session.get(IdentityUser, owner).email == "owner@example.com"
        assert session.get(IdentityUser, other).email == "taken@example.com"


@pytest.mark.parametrize("proof", ["other_account", "other_session", "login", "credentials"])
def test_email_binding_proof_cannot_be_reused_for_another_purpose_or_session(
    identity_app, proof
) -> None:
    app, client, mail, store = identity_app
    owner = create_account(app, "link.first", "first@example.com")
    create_account(app, "link.second")
    login(client, "link.first")
    if proof in {"login", "credentials"}:
        purpose = "login" if proof == "login" else "credentials_update"
        with app.state.session_factory() as session:
            service = IdentityService(session, app.state.settings, verification=store)
            identity = service.authenticate(client.cookies.get("hotkey_session"))
            binding = service._email_binding(identity) if proof == "credentials" else None
        challenge = issue_email(app, store, "proof@example.com", purpose, binding)
        payload = {"challenge_id": challenge.challenge_id, "code": challenge.code}
    else:
        payload = link_code(client, mail, "proof@example.com")
        client.cookies.clear()
        login(client, "link.second" if proof == "other_account" else "link.first")
    response = client.put("/api/identity/email/link", headers=write_headers(client), json=payload)
    assert response.status_code == 401 and response.json()["code"] == "invalid_email_code"
    with app.state.session_factory() as session:
        assert session.get(IdentityUser, owner).email == "first@example.com"


def github_link_flow(app: FastAPI, client: TestClient, provider_id: str = "98765") -> str:
    from urllib.parse import parse_qs, urlsplit

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("access_token"):
            return httpx.Response(
                200, json={"access_token": "controlled-token", "token_type": "bearer"}
            )
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": int(provider_id)})
        return httpx.Response(
            200, json=[{"email": "different.github@example.com", "verified": True, "primary": True}]
        )

    app.state.identity_github = GitHubAdapter(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "test-app",
        "test-secret",
        app.state.settings.web_origin + "/api/identity/github/callback",
    )
    started = client.post("/api/identity/github/link", headers=write_headers(client))
    assert started.status_code == 200, started.text
    params = parse_qs(urlsplit(started.json()["authorization_url"]).query)
    assert params["scope"] == ["user:email"]
    return params["state"][0]


def test_email_account_explicitly_connects_github_with_a_different_email(identity_app) -> None:
    app, client, _mail, _store = identity_app
    owner = create_account(app, "github.link.owner", "email.login@example.com")
    login(client, "github.link.owner")
    old_token = client.cookies["hotkey_session"]
    state = github_link_flow(app, client)
    result = client.get(
        "/api/identity/github/callback",
        params={"state": state, "code": "controlled-code"},
        follow_redirects=False,
    )
    assert result.status_code == 303 and result.headers["location"] == "/account?linked=github"
    view = client.get("/api/identity/session").json()["user"]
    assert (
        view["id"] == str(owner)
        and view["email"] == "email.login@example.com"
        and view["github_connected"] is True
    )
    assert client.cookies["hotkey_session"] != old_token
    assert (
        client.get(
            "/api/identity/session", headers={"Cookie": f"hotkey_session={old_token}"}
        ).status_code
        == 401
    )
    with app.state.session_factory() as session:
        assert session.get(IdentityUser, owner).github_user_id == "98765"
        assert len(session.scalars(select(IdentityUser)).all()) == 1


@pytest.mark.parametrize("failure", ["conflict", "switch", "logout", "cancel", "replace"])
def test_github_link_rejects_conflicts_changed_sessions_and_cancel(identity_app, failure) -> None:
    app, client, _mail, _store = identity_app
    owner = create_account(app, "github.link.first", "first@example.com")
    other = create_account(app, "github.link.second", "second@example.com")
    if failure == "conflict":
        with app.state.session_factory() as session, session.begin():
            session.get(IdentityUser, other).github_user_id = "98765"
    elif failure == "replace":
        with app.state.session_factory() as session, session.begin():
            session.get(IdentityUser, owner).github_user_id = "55555"
    login(client, "github.link.first")
    state = github_link_flow(app, client)
    binding = client.cookies["hotkey_oauth"]
    if failure == "switch":
        client.cookies.clear()
        login(client, "github.link.second")
        client.cookies.set("hotkey_oauth", binding)
    if failure == "logout":
        client.delete("/api/identity/session", headers=write_headers(client))
    params = (
        {"state": state, "error": "access_denied"}
        if failure == "cancel"
        else {"state": state, "code": "controlled-code"}
    )
    result = client.get("/api/identity/github/callback", params=params, follow_redirects=False)
    assert result.status_code == 303
    assert "error=" in result.headers["location"]
    assert result.headers["location"].startswith("/account?")
    with app.state.session_factory() as session:
        assert session.get(IdentityUser, owner).github_user_id == (
            "55555" if failure == "replace" else None
        )
        assert session.get(IdentityUser, owner).credential_version == 1


def test_binding_endpoints_require_authentication_and_csrf(identity_app) -> None:
    app, client, _mail, _store = identity_app
    endpoints = [
        ("post", "/api/identity/email/link/challenges", {"email": "new@example.com"}),
        ("put", "/api/identity/email/link", {"challenge_id": str(uuid4()), "code": "123456"}),
        ("post", "/api/identity/github/link", None),
    ]
    for method, path, payload in endpoints:
        assert client.request(method, path, json=payload).status_code == 401
    create_account(app, "csrf.link")
    login(client, "csrf.link")
    for method, path, payload in endpoints:
        assert (
            client.request(method, path, json=payload, headers={"X-HotKey-CSRF": "1"}).status_code
            == 403
        )


@pytest.mark.parametrize(
    "change", ["ownership", "revoked", "expired", "credential_version", "user_version"]
)
def test_email_link_rechecks_locked_session_after_ownership_verification(
    identity_app, change
) -> None:
    app, client, mail, store = identity_app
    owner = create_account(app, "recheck.link", "original@example.com")
    other = create_account(app, "recheck.other")
    created = login(client, "recheck.link")
    with app.state.session_factory() as session:
        identity = IdentityService(session, app.state.settings).authenticate(
            client.cookies["hotkey_session"]
        )
    proof = link_code(client, mail, "verified@example.com")
    changes = {
        "ownership": {"user_id": other},
        "revoked": {"revoked_at": datetime.now(UTC), "revoked_reason": "logout"},
        "expired": {
            "created_at": datetime.now(UTC) - timedelta(hours=2),
            "expires_at": datetime.now(UTC) - timedelta(hours=1),
        },
        "credential_version": {"credential_version": 2},
    }
    with app.state.session_factory() as session, session.begin():
        if change == "user_version":
            session.execute(
                update(IdentityUser).where(IdentityUser.id == owner).values(credential_version=2)
            )
        else:
            session.execute(
                update(IdentitySession)
                .where(IdentitySession.id == identity.session_id)
                .values(**changes[change])
            )
    with (
        app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="invalid_session"),
    ):
        IdentityService(session, app.state.settings, verification=store).link_email(
            identity=identity,
            challenge_id=UUID(proof["challenge_id"]),
            code=proof["code"],
            client_ip="127.0.0.1",
        )
    with app.state.session_factory() as session:
        assert session.get(IdentityUser, owner).email == "original@example.com"
        assert session.get(IdentityUser, other).email is None
        assert session.get(IdentityUser, owner).credential_version == (
            2 if change == "user_version" else 1
        )
    assert created.json()["user"]["id"] == str(owner)


def test_parallel_email_claims_have_one_winner_and_roll_back_the_other_session(
    identity_app,
) -> None:
    app, client, _mail, _store = identity_app
    identities = []
    tokens = []
    for username in ("parallel.link.first", "parallel.link.second"):
        create_account(app, username)
        client.cookies.clear()
        login(client, username)
        tokens.append(client.cookies["hotkey_session"])
        with app.state.session_factory() as session:
            identities.append(IdentityService(session, app.state.settings).authenticate(tokens[-1]))

    def claim(identity):
        with app.state.session_factory() as session:
            try:
                IdentityService(session, app.state.settings)._link_identity(
                    identity, email="single.owner@example.com"
                )
                return "linked"
            except ApplicationError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, identities))
    assert sorted(results) == ["identity_link_conflict", "linked"]
    for identity, token, result in zip(identities, tokens, results, strict=True):
        with app.state.session_factory() as session:
            user = session.get(IdentityUser, identity.view.user.id)
            assert user.email == ("single.owner@example.com" if result == "linked" else None)
        with app.state.session_factory() as session:
            if result == "linked":
                with pytest.raises(ApplicationError, match="invalid_session"):
                    IdentityService(session, app.state.settings).authenticate(token)
            else:
                assert (
                    IdentityService(session, app.state.settings).authenticate(token).view.user.id
                    == identity.view.user.id
                )


@pytest.mark.parametrize("return_to", ["/sources", "/jobs?state=failed", "//bad.example"])
def test_new_github_registration_requires_username_password_setup(identity_app, return_to) -> None:
    app, client, _mail, _store = identity_app

    def github(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "test-token", "token_type": "bearer"})
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 999123})
        return httpx.Response(
            200, json=[{"email": "new.github@example.com", "primary": True, "verified": True}]
        )

    with httpx.Client(transport=httpx.MockTransport(github)) as http:
        app.state.identity_github = GitHubAdapter(
            http,
            "test-app",
            "test-secret",
            app.state.settings.web_origin + "/api/identity/github/callback",
        )
        started = client.post(
            "/api/identity/github/authorize",
            headers={"X-HotKey-CSRF": "1"},
            json={"return_to": return_to},
        )
        state = httpx.URL(started.json()["authorization_url"]).params["state"]
        callback = client.get(
            "/api/identity/github/callback",
            params={"state": state, "code": "test-code"},
            follow_redirects=False,
        )
        target = httpx.URL(callback.headers["location"])
        assert callback.status_code == 303
        assert target.path == "/account"
        assert target.params["setup"] == "1"
        assert target.params["returnTo"] == ("/topics" if return_to.startswith("//") else return_to)
        initial = client.get("/api/identity/session").json()
        assert initial["user"]["has_password"] is False
        changed = client.put(
            "/api/identity/credentials",
            headers=write_headers(client),
            json={"username": "chosen.github", "password": PASSWORD},
        )
        assert changed.status_code == 200
        assert changed.json()["user"]["id"] == initial["user"]["id"]
        assert changed.json()["user"]["username"] == "chosen.github"
        assert changed.json()["user"]["has_password"] is True
        for identifier in ("chosen.github", "new.github@example.com"):
            client.cookies.clear()
            assert login(client, identifier).json()["user"]["id"] == initial["user"]["id"]


@pytest.mark.parametrize("failure_point", ["session_write", "commit"])
def test_email_identity_failure_rolls_back_proof_and_account(
    identity_app, monkeypatch, failure_point
) -> None:
    from sqlalchemy import event

    app, _client, _mail, store = identity_app
    challenge = issue_email(app, store, "rollback@example.com")
    with app.state.session_factory() as session:
        service = IdentityService(session, app.state.settings, verification=store)

        def fail(*args, **kwargs):
            raise RuntimeError("injected transaction failure")

        if failure_point == "session_write":
            with monkeypatch.context() as patch:
                patch.setattr(service, "_new_session", fail)
                with pytest.raises(RuntimeError, match="injected"):
                    service.verify_email(
                        challenge_id=UUID(challenge.challenge_id),
                        code=challenge.code,
                        client_ip="10.0.0.2",
                        browser_binding=NONCE,
                    )
        else:
            injected = []

            def fail_identity_commit(current):
                row = current.scalar(select(IdentityEmailChallenge))
                if row is not None and row.consumed_at is not None:
                    assert current.scalars(select(IdentityUser)).all()
                    assert current.scalars(select(IdentitySession)).all()
                    injected.append(True)
                    fail()

            event.listen(session, "before_commit", fail_identity_commit)
            try:
                with pytest.raises(RuntimeError, match="injected"):
                    service.verify_email(
                        challenge_id=UUID(challenge.challenge_id),
                        code=challenge.code,
                        client_ip="10.0.0.2",
                        browser_binding=NONCE,
                    )
            finally:
                event.remove(session, "before_commit", fail_identity_commit)
            assert injected == [True]
    with app.state.session_factory() as session:
        assert session.scalar(select(IdentityEmailChallenge)).consumed_at is None
        assert session.scalars(select(IdentityUser)).all() == []
        assert session.scalars(select(IdentitySession)).all() == []
    created = redeem_email(app, store, challenge)
    assert created.view.user.email == "rollback@example.com"
    # Dropping the successful response does not make the committed code reusable.
    with pytest.raises(ApplicationError, match="invalid_email_code"):
        redeem_email(app, store, challenge)
    with app.state.session_factory() as session:
        assert len(session.scalars(select(IdentitySession)).all()) == 1


def test_email_browser_binding_and_resend_keep_only_latest_proof(identity_app) -> None:
    app, client, mail, store = identity_app
    email = "browser@example.com"
    first = client.post(
        "/api/identity/email/challenges", headers={"X-HotKey-CSRF": "1"}, json={"email": email}
    )
    assert first.status_code == 200, first.text
    nonce = client.cookies.get("hotkey_email_browser")
    assert len(nonce) == 43
    cookie = first.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Path=/api/identity" in cookie and "Max-Age=300" in cookie
    old = {"challenge_id": first.json()["challenge_id"], "code": mail.codes[email]}
    with TestClient(app, base_url=app.state.settings.web_origin) as other:
        other.headers["Origin"] = app.state.settings.web_origin
        rejected = other.post(
            "/api/identity/email/sessions", headers={"X-HotKey-CSRF": "1"}, json=old
        )
        assert rejected.status_code == 401 and rejected.json()["code"] == "invalid_email_code"
    store._redis.delete(store._key("email-cooldown", email))
    second = client.post(
        "/api/identity/email/challenges", headers={"X-HotKey-CSRF": "1"}, json={"email": email}
    )
    assert second.status_code == 200 and client.cookies.get("hotkey_email_browser") == nonce
    assert second.json()["challenge_id"] != old["challenge_id"]
    rejected = client.post("/api/identity/email/sessions", headers={"X-HotKey-CSRF": "1"}, json=old)
    assert rejected.status_code == 401
    accepted = client.post(
        "/api/identity/email/sessions",
        headers={"X-HotKey-CSRF": "1"},
        json={"challenge_id": second.json()["challenge_id"], "code": mail.codes[email]},
    )
    assert accepted.status_code == 200, accepted.text


@pytest.mark.parametrize("lock_target", ["challenge", "user"])
def test_email_proof_expiry_is_rechecked_after_waiting_for_lock(identity_app, lock_target) -> None:
    import time

    from sqlalchemy import text

    app, _client, _mail, store = identity_app
    email = "lock.expiry@example.com"
    owner = create_account(app, "lock.expiry", email)
    challenge = issue_email(app, store, email)
    with app.state.session_factory() as session, session.begin():
        row = session.scalar(select(IdentityEmailChallenge))
        row.expires_at = datetime.now(UTC) + timedelta(seconds=1)
    with app.state.session_factory() as blocker, blocker.begin():
        if lock_target == "challenge":
            blocker.scalar(select(IdentityEmailChallenge).with_for_update())
        else:
            blocker.get(IdentityUser, owner, with_for_update=True)

        def attempt():
            try:
                redeem_email(app, store, challenge)
                return "unexpected success"
            except ApplicationError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(attempt)
            # Verify the request has reached a real PG lock, then let expiry pass.
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                blocker.execute(text("SELECT pg_stat_clear_snapshot()"))
                waiting = blocker.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND wait_event_type='Lock'"
                    )
                )
                if waiting:
                    break
                time.sleep(0.01)
            time.sleep(1.1)
            blocker.commit()
            result = future.result(timeout=5)
            assert waiting
            assert result == "invalid_email_code"
    with app.state.session_factory() as session:
        assert session.scalars(select(IdentitySession)).all() == []
        assert session.scalar(select(IdentityEmailChallenge)).consumed_at is None


def test_email_failed_delivery_cannot_invalidate_a_newer_resend(identity_app) -> None:
    app, _client, _mail, store = identity_app
    older = issue_email(app, store, "delivery.race@example.com")
    store._redis.delete(store._key("email-cooldown", "delivery.race@example.com"))
    newer = issue_email(app, store, "delivery.race@example.com")
    with app.state.session_factory() as session:
        EmailChallenges(session, store).invalidate(UUID(older.challenge_id))
    assert redeem_email(app, store, newer).view.user.email == "delivery.race@example.com"


@pytest.mark.parametrize(
    "column,value",
    [
        ("scope_digest", b"short"),
        ("binding_digest", b"short"),
        ("code_digest", b"short"),
        ("purpose", "other"),
        ("attempt_count", -1),
        ("attempt_count", 6),
        ("expires_at", datetime(2000, 1, 1, tzinfo=UTC)),
        ("invalidated_at", datetime.now(UTC)),
    ],
)
def test_email_challenge_database_rejects_invalid_states(identity_app, column, value) -> None:
    from sqlalchemy.exc import IntegrityError

    app, _client, _mail, store = identity_app
    challenge = issue_email(app, store, "constraints@example.com")
    redeem_email(app, store, challenge)
    with app.state.session_factory() as session, pytest.raises(IntegrityError), session.begin():
        session.execute(update(IdentityEmailChallenge).values({column: value}))


@pytest.mark.parametrize("expire_retry", [False, True])
def test_email_unique_account_retry_revalidates_its_own_proof(
    identity_app, monkeypatch, expire_retry
) -> None:
    from threading import Barrier

    app, _client, _mail, store = identity_app
    first = issue_email(app, store, "unique.race@example.com")
    store._redis.delete(store._key("email-cooldown", "unique.race@example.com"))
    with app.state.session_factory() as session:
        second = EmailChallenges(session, store).issue(
            "unique.race@example.com",
            "10.0.0.1",
            "login",
            EmailChallenges(session, store).browser_binding("c" * 43),
        )
    barrier = Barrier(2)
    # Synchronize both missing-account reads before either INSERT can succeed.

    from sqlalchemy.orm import Session

    original_flush = Session.flush
    seen = set()

    def synchronized_flush(session, *args, **kwargs):
        if any(isinstance(row, IdentityUser) for row in session.new) and id(session) not in seen:
            seen.add(id(session))
            barrier.wait(timeout=5)
        return original_flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", synchronized_flush)
    # For the losing insertion, expire its proof after the unique failure rollback.
    original_transaction = IdentityService._write_transaction
    from contextlib import contextmanager

    attempts = {}

    @contextmanager
    def observed_transaction(service, proof=None):
        key = proof.challenge_id if proof else None
        attempts[key] = attempts.get(key, 0) + 1
        if expire_retry and attempts[key] == 2:
            with app.state.session_factory() as other, other.begin():
                row = other.scalar(
                    select(IdentityEmailChallenge).where(IdentityEmailChallenge.challenge_id == key)
                )
                row.created_at = datetime.now(UTC) - timedelta(minutes=6)
                row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        with original_transaction(service, proof) as email:
            yield email

    monkeypatch.setattr(IdentityService, "_write_transaction", observed_transaction)

    def redeem(value):
        challenge, nonce = value
        try:
            return redeem_email(app, store, challenge, nonce=nonce).view.user.id
        except ApplicationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(redeem, [(first, NONCE), (second, "c" * 43)]))
    assert sorted(attempts.values()) == [1, 2]
    if expire_retry:
        assert results.count("invalid_email_code") == 1
    else:
        assert results[0] == results[1]
    with app.state.session_factory() as session:
        assert len(session.scalars(select(IdentityUser)).all()) == 1
        assert len(session.scalars(select(IdentitySession)).all()) == (1 if expire_retry else 2)


def test_email_expiry_cleanup_commits_before_concurrent_resends(identity_app, monkeypatch) -> None:
    from threading import Barrier

    app, _client, _mail, store = identity_app
    first = issue_email(app, store, "cleanup.first@example.com")
    second = issue_email(app, store, "cleanup.second@example.com")
    with app.state.session_factory() as session, session.begin():
        session.execute(
            update(IdentityEmailChallenge).values(
                created_at=datetime.now(UTC) - timedelta(minutes=6),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    for email in ("cleanup.first@example.com", "cleanup.second@example.com"):
        store._redis.delete(store._key("email-cooldown", email))
    barrier = Barrier(2)
    original = EmailChallenges.prune

    def synchronized_cleanup(domain):
        original(domain)
        assert not domain.session.in_transaction()
        barrier.wait(timeout=5)

    monkeypatch.setattr(EmailChallenges, "prune", synchronized_cleanup)
    with ThreadPoolExecutor(max_workers=2) as executor:
        renewed = list(
            executor.map(
                lambda email: issue_email(app, store, email),
                ["cleanup.second@example.com", "cleanup.first@example.com"],
            )
        )
    assert {value.challenge_id for value in renewed}.isdisjoint(
        {first.challenge_id, second.challenge_id}
    )
    with app.state.session_factory() as session:
        assert len(session.scalars(select(IdentityEmailChallenge)).all()) == 2


@pytest.mark.parametrize("operation", ["link", "credentials"])
def test_sensitive_email_transaction_failure_preserves_proof_and_session(
    identity_app, monkeypatch, operation
) -> None:
    app, client, mail, _store = identity_app
    owner = create_account(app, "sensitive.owner", "sensitive@example.com")
    login(client, "sensitive.owner")
    previous = client.cookies.get("hotkey_session")
    if operation == "link":
        payload = link_code(client, mail, "new.sensitive@example.com")
        endpoint = "/api/identity/email/link"
    else:
        sent = client.post(
            "/api/identity/email/challenges",
            headers=write_headers(client),
            json={"email": "sensitive@example.com"},
        )
        assert sent.status_code == 200
        payload = {
            "challenge_id": sent.json()["challenge_id"],
            "code": mail.codes["sensitive@example.com"],
            "username": "sensitive.changed",
            "password": "new-sensitive-password-123",
        }
        endpoint = "/api/identity/credentials"

    def fail(*args, **kwargs):
        raise RuntimeError("injected sensitive failure")

    with monkeypatch.context() as patch:
        patch.setattr(IdentityService, "_new_session", fail)
        with pytest.raises(RuntimeError, match="injected sensitive"):
            client.put(endpoint, headers=write_headers(client), json=payload)
    with app.state.session_factory() as session:
        user = session.get(IdentityUser, owner)
        assert user.email == "sensitive@example.com" and user.credential_version == 1
        assert session.scalar(select(IdentityEmailChallenge)).consumed_at is None
        assert len(session.scalars(select(IdentitySession)).all()) == 1
    assert client.get("/api/identity/session").status_code == 200
    retried = client.put(endpoint, headers=write_headers(client), json=payload)
    assert retried.status_code == 200, retried.text
    assert client.cookies.get("hotkey_session") != previous
    assert (
        client.get(
            "/api/identity/session", headers={"Cookie": f"hotkey_session={previous}"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("binding_change", ["session", "credential_version"])
def test_credential_email_proof_rejects_new_binding_generation(
    identity_app, binding_change
) -> None:
    app, client, mail, _store = identity_app
    owner = create_account(app, "generation.owner", "generation@example.com")
    login(client, "generation.owner")
    sent = client.post(
        "/api/identity/email/challenges",
        headers=write_headers(client),
        json={"email": "generation@example.com"},
    )
    assert sent.status_code == 200
    if binding_change == "session":
        client.cookies.clear()
        login(client, "generation.owner")
    else:
        with app.state.session_factory() as session, session.begin():
            session.get(IdentityUser, owner).credential_version = 2
            session.execute(
                update(IdentitySession)
                .where(IdentitySession.user_id == owner)
                .values(credential_version=2)
            )
    rejected = client.put(
        "/api/identity/credentials",
        headers=write_headers(client),
        json={
            "challenge_id": sent.json()["challenge_id"],
            "code": mail.codes["generation@example.com"],
            "username": "generation.changed",
            "password": "generation-password-123",
        },
    )
    assert rejected.status_code == 401 and rejected.json()["code"] == "invalid_email_code"
    with app.state.session_factory() as session:
        assert session.get(IdentityUser, owner).username == "generation.owner"
        assert session.scalar(select(IdentityEmailChallenge)).consumed_at is None
