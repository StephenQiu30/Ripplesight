from __future__ import annotations

import re
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic
from urllib.parse import urlencode

import httpx

from core.errors import ApplicationError

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_EMAILS_URL = "https://api.github.com/user/emails"
_API_VERSION = "2026-03-10"
_AUTHENTICATION_DEADLINE_SECONDS = 10


@dataclass(frozen=True)
class GitHubIdentity:
    user_id: str
    email: str


class GitHubAdapter:
    def __init__(
        self,
        client: httpx.Client,
        client_id: str | None,
        client_secret: str | None,
        redirect_uri: str | None,
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def _require_configuration(self) -> None:
        if not self._client_id or not self._client_secret or not self._redirect_uri:
            raise ApplicationError("auth_dependency_unavailable")

    def authorization_url(self, state: str, challenge: str) -> str:
        self._require_configuration()
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{_AUTHORIZE_URL}?{query}"

    def authenticate(self, code: str, verifier: str) -> GitHubIdentity:
        self._require_configuration()
        if not code or len(code) > 512 or not re.fullmatch(r"[A-Za-z0-9_~.\-]{43,128}", verifier):
            raise ApplicationError("github_authentication_failed")
        deadline = monotonic() + _AUTHENTICATION_DEADLINE_SECONDS
        cancelled = Event()
        results: Queue[GitHubIdentity | None] = Queue(maxsize=1)

        def verify() -> None:
            try:
                value = self._authenticate_once(code, verifier, deadline, cancelled)
            except Exception:
                value = None
            results.put(value)

        # HTTPX timeouts apply to individual network phases. This also bounds DNS
        # and the aggregate exchange; a late worker cannot create a product session.
        Thread(target=verify, name="identity-github-verification", daemon=True).start()
        try:
            identity = results.get(timeout=max(0, deadline - monotonic()))
        except Empty:
            cancelled.set()
            raise ApplicationError("github_authentication_failed") from None
        if identity is None:
            raise ApplicationError("github_authentication_failed")
        return identity

    def _authenticate_once(
        self, code: str, verifier: str, deadline: float, cancelled: Event
    ) -> GitHubIdentity:
        try:
            response = self._client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "code": code,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
                timeout=self._remaining(deadline, cancelled),
                follow_redirects=False,
            )
            response.raise_for_status()
            token_data = response.json()
            if not isinstance(token_data, dict):
                raise ValueError("invalid provider response")
            access_token = token_data.get("access_token")
            if (
                not isinstance(access_token, str)
                or not access_token
                or len(access_token) > 1024
                or token_data.get("token_type", "").lower() != "bearer"
                or token_data.get("error")
            ):
                raise ValueError("invalid provider token")
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": _API_VERSION,
            }
            user_response = self._client.get(
                _USER_URL,
                headers=headers,
                timeout=self._remaining(deadline, cancelled),
                follow_redirects=False,
            )
            user_response.raise_for_status()
            user = user_response.json()
            if not isinstance(user, dict):
                raise ValueError("invalid provider user")
            user_id = user.get("id")
            if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
                raise ValueError("invalid provider user ID")
            email_response = self._client.get(
                _EMAILS_URL,
                headers=headers,
                params={"per_page": 100},
                timeout=self._remaining(deadline, cancelled),
                follow_redirects=False,
            )
            email_response.raise_for_status()
            emails = email_response.json()
            self._remaining(deadline, cancelled)
            if not isinstance(emails, list):
                raise ValueError("invalid provider email response")
            verified = [
                item.get("email")
                for item in emails
                if isinstance(item, dict)
                and item.get("primary") is True
                and item.get("verified") is True
            ]
            if len(verified) != 1:
                raise ValueError("verified primary email required")
            email = verified[0]
            if (
                not isinstance(email, str)
                or len(email) > 254
                or not re.fullmatch(r"[^\s@\x00-\x1f\x7f]+@[^\s@\x00-\x1f\x7f]+", email)
            ):
                raise ValueError("invalid provider email")
            return GitHubIdentity(str(user_id), email.strip().lower())
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise ApplicationError("github_authentication_failed") from None

    @staticmethod
    def _remaining(deadline: float, cancelled: Event) -> float:
        remaining = deadline - monotonic()
        if remaining <= 0 or cancelled.is_set():
            raise ValueError("provider deadline exceeded")
        return remaining
