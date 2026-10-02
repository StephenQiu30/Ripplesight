"""Explicitly admitted, bounded HTTP reads with per-attempt existing-budget callbacks."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from pydantic import SecretStr

from sources.editorial_schemas import EditorialAuthorization, public_url

type RequestOutcome = Literal["succeeded", "failed", "unknown"]


class EditorialSourceError(RuntimeError):
    def __init__(self, code: str, *, unknown: bool = False, blocked: bool = False) -> None:
        super().__init__(code)
        self.code, self.unknown, self.blocked = code, unknown, blocked


@dataclass(frozen=True, slots=True)
class EditorialHttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8-sig", errors="strict")


class EditorialHttpClient:
    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        authorization: EditorialAuthorization | None = None,
        before_request: Callable[[int], bool] = lambda attempt: False,
        settle_request: Callable[[int, RequestOutcome], None] | None = None,
        cancelled: Callable[[], bool] = lambda: False,
        max_requests: int = 25,
        max_seconds: float = 90,
        transport: httpx.BaseTransport | None = None,
        allow_network: bool = False,
    ) -> None:
        if not 1 <= max_requests <= 100 or not 0 < max_seconds <= 300:
            raise ValueError("invalid source HTTP limits")
        self._hosts = allowed_hosts
        self._authorization = authorization or EditorialAuthorization()
        self._before = before_request
        self._settle = settle_request
        self._cancelled = cancelled
        self._maximum = max_requests
        self._deadline = time.monotonic() + max_seconds
        self._mock = isinstance(transport, httpx.MockTransport)
        self._allow_network = allow_network
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(15, connect=5, pool=5),
            follow_redirects=False,
        )
        self.request_count = 0

    def close(self) -> None:
        self._client.close()

    def _check_url(self, value: str) -> str:
        url = public_url(value)
        host = urlsplit(url).hostname
        if host not in self._hosts:
            raise EditorialSourceError("unapproved_target", blocked=True)
        if not self._mock:
            if not self._allow_network:
                raise EditorialSourceError("real_network_disabled", blocked=True)
            try:
                addresses = socket.getaddrinfo(
                    host,
                    urlsplit(url).port or (443 if url.startswith("https:") else 80),
                    type=socket.SOCK_STREAM,
                )
                if not addresses or any(
                    not ip_address(record[4][0]).is_global for record in addresses
                ):
                    raise EditorialSourceError("unapproved_target", blocked=True)
            except OSError as error:
                raise EditorialSourceError("target_unavailable") from error
        return url

    def request(
        self,
        url: str,
        *,
        method: Literal["GET", "POST"] = "GET",
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        same_origin_redirects: bool = False,
        accepted_statuses: frozenset[int] = frozenset({200}),
        credential_query: Mapping[str, SecretStr] | None = None,
    ) -> EditorialHttpResponse:
        if not self._authorization.allowed or self._settle is None:
            raise EditorialSourceError("source_authorization_required", blocked=True)
        current = self._check_url(url)
        origin = urlsplit(current)
        if credential_query:
            if set(credential_query) != {"key"}:
                raise EditorialSourceError("invalid_runtime_credential", blocked=True)
            same_origin_redirects = True
        request_headers = {"user-agent": "HotKey editorial source collector", **(headers or {})}
        for redirect in range(4):
            if self._cancelled():
                raise EditorialSourceError("cancelled", blocked=True)
            if time.monotonic() >= self._deadline or self.request_count >= self._maximum:
                raise EditorialSourceError("budget_exhausted", blocked=True)
            attempt = self.request_count + 1
            if not self._before(attempt):
                raise EditorialSourceError("budget_exhausted", blocked=True)
            self.request_count = attempt
            outcome: RequestOutcome = "unknown"
            try:
                wire_url = current
                if credential_query:
                    parts = urlsplit(current)
                    wire_url = urlunsplit(
                        (
                            *parts[:3],
                            urlencode(
                                [
                                    *parse_qsl(parts.query),
                                    *(
                                        (key, value.get_secret_value())
                                        for key, value in credential_query.items()
                                    ),
                                ]
                            ),
                            "",
                        )
                    )
                with self._client.stream(
                    method,
                    wire_url,
                    headers=request_headers,
                    content=body,
                    timeout=min(15, max(0.1, self._deadline - time.monotonic())),
                ) as response:
                    outcome = (
                        "succeeded"
                        if response.status_code in accepted_statuses
                        or response.status_code in {301, 302, 303, 307, 308}
                        else "failed"
                    )
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect >= 3:
                            raise EditorialSourceError("redirect_protocol_error")
                        target = self._check_url(urljoin(str(response.url), location))
                        parsed = urlsplit(target)
                        if same_origin_redirects and (parsed.scheme, parsed.netloc) != (
                            origin.scheme,
                            origin.netloc,
                        ):
                            raise EditorialSourceError("cross_origin_redirect", blocked=True)
                        if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
                            request_headers = {
                                key: value
                                for key, value in request_headers.items()
                                if key.casefold() not in {"authorization", "cookie", "x-api-key"}
                            }
                        current = target
                        if response.status_code == 303:
                            method, body = "GET", None
                        continue
                    if response.status_code not in accepted_statuses:
                        code = (
                            "rate_limited"
                            if response.status_code == 429
                            else "authentication_required"
                            if response.status_code == 401
                            else "access_denied"
                            if response.status_code == 403
                            else "upstream_failed"
                            if response.status_code >= 500
                            else "upstream_protocol_error"
                        )
                        raise EditorialSourceError(
                            code, blocked=response.status_code in {401, 403, 429}
                        )
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if self._cancelled() or time.monotonic() >= self._deadline:
                            outcome = "unknown"
                            raise EditorialSourceError("interrupted_response", unknown=True)
                        data.extend(chunk)
                        if len(data) > 4 * 1024 * 1024:
                            raise EditorialSourceError("response_too_large")
                    return EditorialHttpResponse(
                        current, response.status_code, dict(response.headers), bytes(data)
                    )
            except (httpx.HTTPError, TimeoutError):
                outcome = "unknown"
                raise EditorialSourceError("upstream_unknown", unknown=True) from None
            finally:
                self._settle(attempt, outcome)
        raise EditorialSourceError("redirect_protocol_error")
