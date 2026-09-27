from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMETERS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}
)


def _canonical_host(value: str) -> str:
    try:
        return value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("web target host is invalid") from error


def normalize_web_host(value: str) -> str:
    """Normalize one exact public domain used by a versioned web connection."""
    if (
        value != value.strip()
        or not value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("web target host is invalid")
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except ValueError as error:
        raise ValueError("web target host is invalid") from error
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("web target host is invalid")
    host = _canonical_host(parsed.hostname)
    try:
        ip_address(host)
    except ValueError:
        return host
    raise ValueError("web target host must be a public domain")


def normalize_web_url(url: str, *, allowed_hosts: frozenset[str]) -> str:
    """Normalize an allowlisted public HTTP URL without changing path or query meaning."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ValueError("web target URL is invalid") from error
    if (
        url != url.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in url)
        or parsed.scheme.lower() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("web target URL is not allowed")

    scheme = parsed.scheme.lower()
    host = normalize_web_host(parsed.hostname)
    allowed = frozenset(normalize_web_host(item) for item in allowed_hosts)
    if not allowed or host not in allowed:
        raise ValueError("web target host is not allowlisted")
    if port not in {None, 80 if scheme == "http" else 443}:
        raise ValueError("web target port is not allowed")

    path = parsed.path or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))


def normalize_public_article_url(value: str) -> str:
    """Keep semantic query fields while dropping only known tracking fields."""
    if len(value) > 2048:
        raise ValueError("article URL is too long")
    host = urlsplit(value).hostname
    if host is None:
        raise ValueError("article URL has no host")
    local_host = host.rstrip(".").lower()
    if local_host in {"localhost", "local"} or local_host.endswith((".localhost", ".local")):
        raise ValueError("article URL must use a public host")
    normalized = normalize_web_url(value, allowed_hosts=frozenset({host}))
    parts = urlsplit(normalized)
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_PARAMETERS
        ]
    )
    article_url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    if len(article_url) > 2048:
        raise ValueError("article URL is too long")
    return article_url
