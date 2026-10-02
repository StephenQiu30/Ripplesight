"""Bounded parsing rules adapted from AIHOT sources (MIT, THIRD_PARTY_NOTICES.md)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from sources.editorial_html import sanitize_editorial_html
from sources.editorial_schemas import EditorialMaterial, fingerprint, public_url


def collapse(value: str) -> str:
    return " ".join(value.split())


def sanitize_html(value: str, base: str) -> tuple[str, str]:
    html = sanitize_editorial_html(value, base)
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True)).strip()
    if len(text) > 100_000 or len(html) > 500_000:
        raise ValueError("source body exceeds its limit")
    return html, text


def plain(value: str) -> str:
    _, text = sanitize_html(value, "https://example.invalid/")
    return collapse(text)


def get_path(obj: object, path: str) -> Any:
    current = obj
    for part in path.split(".") if path else ():
        if isinstance(current, list) and part.isascii() and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def render_template(template: str, item: object) -> str | None:
    missing = False

    def replace(match: re.Match[str]) -> str:
        nonlocal missing
        value = get_path(item, match[2])
        if value is None or value == "" or isinstance(value, (dict, list, bool)):
            missing = True
            return ""
        return str(value) if match[1] else quote(str(value), safe="/")

    result = re.sub(r"\{(raw:)?([^}]+)\}", replace, template)
    return None if missing else result


def parse_loose_date(value: str | None, utc_offset: str = "+08:00") -> datetime | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            return None
    try:
        direct = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if direct.utcoffset() is not None:
            return direct.astimezone(UTC)
    except ValueError:
        pass
    sign = -1 if utc_offset.startswith("-") else 1
    source_zone = timezone(
        sign * timedelta(hours=int(utc_offset[1:3]), minutes=int(utc_offset[4:6]))
    )
    match = re.search(
        r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:(?:T|\s*)(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        value,
    )
    if match:
        try:
            return datetime(
                int(match[1]),
                int(match[2]),
                int(match[3]),
                int(match[4] or 0),
                int(match[5] or 0),
                int(match[6] or 0),
                tzinfo=source_zone,
            ).astimezone(UTC)
        except ValueError:
            return None
    cleaned = re.sub(r"星期[一二三四五六日天]|(?<=\d)(?:st|nd|rd|th)", "", value)
    try:
        date = parsedate_to_datetime(cleaned)
        return (date.replace(tzinfo=source_zone) if date.utcoffset() is None else date).astimezone(
            UTC
        )
    except (ValueError, TypeError):
        pass
    for pattern in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(cleaned, pattern).replace(tzinfo=source_zone).astimezone(UTC)
        except ValueError:
            pass
    return None


def material(
    url: str, title: str, *, preserve_fragment: bool = False, **kwargs: Any
) -> EditorialMaterial:
    normalized = public_url(url, keep_fragment=preserve_fragment)
    identity = f"url:{normalized}"
    if len(identity) > 512:
        identity = f"url-sha256:{fingerprint(normalized).hex()}"
    identity = kwargs.pop("identity_key", identity)
    kwargs.setdefault("content_format", "html" if kwargs.get("body_html") else "text")
    return EditorialMaterial(
        url=normalized, identity_key=identity, title=collapse(plain(title))[:2000], **kwargs
    )


def embedded_json(text: str, *, window_var: str | None = None, key: str | None = None) -> object:
    decoder = json.JSONDecoder()
    if window_var:
        match = re.search(rf"(?:window\.)?{re.escape(window_var)}\s*=\s*", text)
        if match is None:
            raise ValueError("embedded window variable not found")
        return decoder.raw_decode(text[match.end() :].lstrip())[0]
    if not key:
        raise ValueError("embedded key is required")

    def find(node: object, depth: int = 0) -> object:
        if depth > 12:
            return None
        if isinstance(node, dict):
            if isinstance(node.get(key), list):
                return {key: node[key]}
            children: Iterable[object] = node.values()
        elif isinstance(node, list):
            children = node
        else:
            return None
        for child in children:
            found = find(child, depth + 1)
            if found is not None:
                return found
        return None

    soup = BeautifulSoup(text, "html.parser")
    for node in soup.find_all("script"):
        body = node.get_text().strip()
        try:
            parsed = json.loads(body)
            found = find(parsed)
            if found is not None:
                return found
        except ValueError:
            pass
        # Flight payloads contain JSON strings, never executable JavaScript literals.
        for quoted in re.finditer(r'"(?:[^"\\]|\\.)*"', body):
            try:
                decoded = json.loads(quoted[0])
                at = decoded.find(f'"{key}"')
                if at < 0:
                    continue
                start = decoded.rfind("{", 0, at)
                if start >= 0:
                    found = find(decoder.raw_decode(decoded[start:])[0])
                    if found is not None:
                        return found
            except (ValueError, AttributeError):
                pass
    raise ValueError("embedded JSON key not found")
