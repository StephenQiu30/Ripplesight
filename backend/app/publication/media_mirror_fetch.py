"""Bounded, DNS-pinned public media HTTP, never run from a reading request."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx

from publication.media_mirror_codec import validate_media_header
from sources.adapters.web_targets import normalize_web_url

Outcome = Literal["succeeded", "failed", "unknown", "not_sent"]
Resolver = Callable[[str], tuple[str, ...]]


def resolve_public_addresses(host: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {str(item[4][0]) for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        )
    )


def public_target(url: str, *, resolver: Resolver) -> tuple[str, str, str]:
    source_host = urlsplit(url).hostname
    if source_host is None:
        raise ValueError("media URL has no hostname")
    normalized = normalize_web_url(url, allowed_hosts=frozenset({source_host}))
    host = urlsplit(normalized).hostname
    assert host is not None
    addresses = resolver(host)
    if not addresses or any(not ip_address(address).is_global for address in addresses):
        raise ValueError("media DNS includes a non-public destination")
    # The resolved literal is used for the connection; the original host remains TLS SNI/Host.
    pinned = str(httpx.URL(normalized).copy_with(host=addresses[0]))
    return normalized, pinned, host


@dataclass(frozen=True)
class FetchedMedia:
    body: bytes
    mime_type: str
    final_url: str
    width: int | None
    height: int | None


@dataclass(frozen=True)
class FetchedDocument:
    body: bytes
    final_url: str
    content_type: str


class MediaMirrorClient:
    def __init__(
        self,
        *,
        enabled: bool = False,
        before_request: Callable[[int], bool],
        after_request: Callable[[int, Outcome], None],
        cancelled: Callable[[], bool] = lambda: False,
        resolver: Resolver = resolve_public_addresses,
        transport: httpx.BaseTransport | None = None,
        image_max_bytes: int = 15 * 1024 * 1024,
        video_max_bytes: int = 64 * 1024 * 1024,
        max_redirects: int = 3,
        redirect_hosts: frozenset[str] = frozenset(),
    ) -> None:
        if (
            not 1 <= image_max_bytes <= 15 * 1024 * 1024
            or not 1 <= video_max_bytes <= 128 * 1024 * 1024
            or not 0 <= max_redirects <= 3
        ):
            raise ValueError("invalid media transport bounds")
        self.enabled, self.before, self.after, self.cancelled = (
            enabled,
            before_request,
            after_request,
            cancelled,
        )
        self.resolver, self.redirect_hosts = resolver, redirect_hosts
        self.image_max_bytes, self.video_max_bytes, self.max_redirects = (
            image_max_bytes,
            video_max_bytes,
            max_redirects,
        )
        self.client = httpx.Client(
            timeout=httpx.Timeout(20), transport=transport, follow_redirects=False, trust_env=False
        )

    def close(self) -> None:
        self.client.close()

    def fetch(self, url: str, *, kind: Literal["image", "video"]) -> FetchedMedia:
        def validate(body: bytes, final_url: str, content_type: str) -> FetchedMedia:
            mime, width, height = validate_media_header(body, kind=kind)
            return FetchedMedia(body, mime, final_url, width, height)

        return self._fetch(
            url,
            cap=self.image_max_bytes if kind == "image" else self.video_max_bytes,
            validate=validate,
            accept="image/*,video/*",
        )

    def fetch_document(self, url: str, *, max_bytes: int = 4_000_000) -> FetchedDocument:
        if not 1 <= max_bytes <= 10_000_000:
            raise ValueError("document byte limit must be explicit and at most 10MB")

        def validate(body: bytes, final_url: str, content_type: str) -> FetchedDocument:
            mime = content_type.partition(";")[0].strip().casefold()
            prefix = body[:1024].lstrip().lower()
            if mime not in {"text/html", "application/xhtml+xml"} and not (
                not mime and (prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"))
            ):
                raise ValueError("source icon discovery requires an HTML document")
            return FetchedDocument(body, final_url, content_type)

        return self._fetch(
            url, cap=max_bytes, validate=validate, accept="text/html,application/xhtml+xml"
        )

    def _fetch[T](
        self, url: str, *, cap: int, validate: Callable[[bytes, str, str], T], accept: str
    ) -> T:
        if not self.enabled or self.cancelled():
            raise PermissionError("media external requests are disabled or cancelled")
        deadline = time.monotonic() + 120
        current = url
        original_host = urlsplit(url).hostname
        for index in range(1, self.max_redirects + 2):
            if self.cancelled() or time.monotonic() >= deadline:
                raise PermissionError("media fetch is cancelled or timed out")
            normalized, pinned, host = public_target(current, resolver=self.resolver)
            if host != original_host and host not in self.redirect_hosts:
                raise ValueError("redirect host is not explicitly allowed")
            if not self.before(index):
                raise PermissionError("media budget or lease denied this request")
            outcome: Outcome = "unknown"
            try:
                with self.client.stream(
                    "GET",
                    pinned,
                    headers={
                        "Host": host,
                        "Accept-Encoding": "identity",
                        "User-Agent": "HotKey-Media/1.0",
                        "Accept": accept,
                    },
                    extensions={"sni_hostname": host},
                ) as response:
                    outcome = "failed"
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or index > self.max_redirects:
                            raise ValueError("media redirect limit or missing location")
                        current = urljoin(normalized, location)
                        outcome = "succeeded"
                        continue
                    response.raise_for_status()
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ValueError("compressed media transfer is not admitted")
                    length = response.headers.get("content-length")
                    if length and (not length.isdecimal() or int(length) > cap):
                        raise ValueError("media byte limit")
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        if (
                            self.cancelled()
                            or time.monotonic() >= deadline
                            or len(body) + len(chunk) > cap
                        ):
                            raise ValueError("media cancelled, timed out or over byte limit")
                        body.extend(chunk)
                    result = validate(
                        bytes(body), normalized, response.headers.get("content-type", "")
                    )
                    outcome = "succeeded"
                    return result
            except (httpx.TransportError, TimeoutError):
                outcome = "unknown"
                raise
            finally:
                self.after(index, outcome)
        raise ValueError("media redirect limit")
