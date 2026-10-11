from __future__ import annotations

import ssl
from queue import Empty, Queue
from threading import Event
from time import monotonic

import httpx
import pytest

from core.errors import ApplicationError
from identity.adapters import email as email_module
from identity.adapters import github as github_module
from identity.adapters.email import SmtpEmailAdapter
from identity.adapters.github import GitHubAdapter


def test_oauth_app_requests_only_email_read_scope_with_pkce() -> None:
    with httpx.Client() as client:
        adapter = GitHubAdapter(client, "test-client", "secret", "https://example.com/callback")
        url = httpx.URL(adapter.authorization_url("state", "challenge"))

    assert url.params["scope"] == "user:email"
    assert url.params["code_challenge_method"] == "S256"
    assert url.params["redirect_uri"] == "https://example.com/callback"
    assert url.params["state"] == "state"


@pytest.mark.parametrize(
    "emails",
    [
        [{"email": "user@example.com", "primary": True, "verified": False}],
        [{"email": "user@example.com", "primary": False, "verified": True}],
        [
            {"email": "user@example.com", "primary": True, "verified": True},
            {"email": "other@example.com", "primary": True, "verified": True},
        ],
        {"email": "user@example.com", "primary": True, "verified": True},
    ],
)
def test_github_requires_one_verified_primary_email(emails: object) -> None:
    def provider(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "test-token", "token_type": "bearer"})
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 123})
        return httpx.Response(200, json=emails)

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        adapter = GitHubAdapter(client, "app", "secret", "https://example.com/callback")
        with pytest.raises(ApplicationError, match="github_authentication_failed"):
            adapter.authenticate("code", "v" * 43)


def test_github_overall_deadline_prevents_late_follow_up_calls(monkeypatch) -> None:
    monkeypatch.setattr(github_module, "_AUTHENTICATION_DEADLINE_SECONDS", 0.02)
    release = Event()
    finished = Event()
    paths: list[str] = []

    def provider(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        release.wait(timeout=1)
        finished.set()
        return httpx.Response(200, json={"access_token": "test-token", "token_type": "bearer"})

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        adapter = GitHubAdapter(client, "app", "secret", "https://example.com/callback")
        started = monotonic()
        try:
            with pytest.raises(ApplicationError, match="github_authentication_failed"):
                adapter.authenticate("code", "v" * 43)
            assert monotonic() - started < 0.5
        finally:
            release.set()
        assert finished.wait(timeout=1)
        assert paths == ["/login/oauth/access_token"]


def test_smtp_checks_tls_before_authentication_and_delivery(monkeypatch) -> None:
    calls: list[str] = []

    class SMTP:
        sock = None

        def __init__(self, **kwargs: object) -> None:
            calls.append("connect")
            assert kwargs["local_hostname"] == "localhost"
            assert 0 < float(kwargs["timeout"]) <= 10

        def ehlo(self) -> None:
            calls.append("ehlo")

        def starttls(self, *, context: ssl.SSLContext) -> None:
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            calls.append("tls")

        def login(self, username: str, password: str) -> None:
            assert (username, password) == ("smtp-user", "smtp-password")
            calls.append("auth")

        def send_message(self, message) -> dict[str, object]:
            assert message["To"] == "user@example.com"
            assert "123456" in message.get_content()
            calls.append("send")
            return {}

        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(email_module.smtplib, "SMTP", SMTP)
    SmtpEmailAdapter(
        "smtp.example.com", 587, "starttls", "smtp-user", "smtp-password", "sender@example.com"
    ).send_code("user@example.com", "123456")
    assert calls == ["connect", "ehlo", "tls", "ehlo", "auth", "send", "close"]


@pytest.mark.parametrize("blocked_stage", ["tls_context", "dns"])
def test_smtp_deadline_prevents_late_setup_from_sending(
    monkeypatch: pytest.MonkeyPatch, blocked_stage: str
) -> None:
    """A timeout can occur before or after an SMTP connection is constructed."""
    clock = [100.0]
    monkeypatch.setattr(email_module, "monotonic", lambda: clock[0])
    monkeypatch.setattr(email_module, "_DELIVERY_DEADLINE_SECONDS", 10)
    setup_started = Event()
    release = Event()
    finished = Event()
    connected: list[object] = []
    closed: list[object] = []
    sent: list[object] = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    def block_setup() -> None:
        setup_started.set()
        assert release.wait(timeout=5), "test did not release SMTP setup"

    def create_context() -> ssl.SSLContext:
        if blocked_stage == "tls_context":
            block_setup()
        return context

    class DeadlineQueue(Queue[bool]):
        def get(self, block: bool = True, timeout: float | None = None) -> bool:
            # Establish which setup stage is blocked before expiring the caller's wait.
            # This avoids depending on thread scheduling or trust-store load time.
            assert setup_started.wait(timeout=5), "SMTP worker did not reach the setup stage"
            assert timeout == pytest.approx(10)
            clock[0] += 10
            raise Empty

        def put(self, item: bool, block: bool = True, timeout: float | None = None) -> None:
            super().put(item, block=block, timeout=timeout)
            finished.set()

    class SMTP:
        sock = None

        def __init__(self, **kwargs: object) -> None:
            connected.append(self)
            if blocked_stage == "dns":
                block_setup()

        def ehlo(self) -> None:
            pass

        def starttls(self, **kwargs: object) -> None:
            pass

        def send_message(self, message) -> dict[str, object]:
            sent.append(message)
            return {}

        def close(self) -> None:
            closed.append(self)

    monkeypatch.setattr(email_module.ssl, "create_default_context", create_context)
    monkeypatch.setattr(email_module, "Queue", DeadlineQueue)
    monkeypatch.setattr(email_module.smtplib, "SMTP", SMTP)
    adapter = SmtpEmailAdapter(
        "smtp.example.com", 587, "starttls", None, None, "sender@example.com"
    )
    try:
        with pytest.raises(ApplicationError, match="email_delivery_unavailable"):
            adapter.send_code("user@example.com", "123456")
    finally:
        release.set()
    assert finished.wait(timeout=5)
    assert len(connected) == (1 if blocked_stage == "dns" else 0)
    assert closed == connected
    assert sent == []
