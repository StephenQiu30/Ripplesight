"""Bounded parsing rules adapted from AIHOT sources (MIT, THIRD_PARTY_NOTICES.md)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone
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


_DATE_ZONE = r"Z|GMT|UTC?|[EMP][SD]T|CDT|CST|[+-]\d{2}:?\d{2}"


def _date_zone(explicit: str, source_zone: timezone) -> timezone:
    offsets = {
        "EST": -5,
        "EDT": -4,
        "MST": -7,
        "MDT": -6,
        "PST": -8,
        "PDT": -7,
        "CDT": -5,
        "Z": 0,
        "GMT": 0,
        "UTC": 0,
        "UT": 0,
    }
    explicit = explicit.upper()
    if explicit in offsets:
        return timezone(timedelta(hours=offsets[explicit]))
    if explicit.startswith(("+", "-")):
        offset = explicit.replace(":", "")
        if int(offset[3:]) > 59:
            raise ValueError("invalid date timezone")
        return timezone(
            (1 if offset[0] == "+" else -1)
            * timedelta(hours=int(offset[1:3]), minutes=int(offset[3:]))
        )
    # CST is ambiguous on Chinese sources; retain the configured source offset.
    return source_zone


def parse_loose_date(value: str | None, utc_offset: str = "+08:00") -> datetime | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            return None
    sign = -1 if utc_offset.startswith("-") else 1
    source_zone = timezone(
        sign * timedelta(hours=int(utc_offset[1:3]), minutes=int(utc_offset[4:6]))
    )
    try:
        direct = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (
            direct.replace(tzinfo=source_zone) if direct.utcoffset() is None else direct
        ).astimezone(UTC)
    except (ValueError, OverflowError):
        pass
    match = re.search(
        r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:(?:T|\s*)(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
        value,
    )
    if match:
        try:
            explicit = re.match(rf"\s*({_DATE_ZONE})(?:\b|$)", value[match.end() :], re.IGNORECASE)
            return datetime(
                int(match[1]),
                int(match[2]),
                int(match[3]),
                int(match[4] or 0),
                int(match[5] or 0),
                int(match[6] or 0),
                tzinfo=_date_zone(explicit[1], source_zone) if explicit else source_zone,
            ).astimezone(UTC)
        except (ValueError, OverflowError):
            return None
    # Read English wall-clock fields directly: neither locale nor host DST is consulted.
    cleaned = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value, flags=re.IGNORECASE)
    month_first = re.search(r"\b([a-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b", cleaned, re.IGNORECASE)
    day_first = re.search(r"\b(\d{1,2})\s+([a-z]{3,9})\s+(\d{4})\b", cleaned, re.IGNORECASE)
    english = month_first or day_first
    if english is None:
        return None
    month, day = (english[1], english[2]) if month_first else (english[2], english[1])
    months = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    clock = re.fullmatch(
        r"\s*(?:(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?\s*)?"
        rf"({_DATE_ZONE})?\s*",
        cleaned[english.end() :],
        re.IGNORECASE,
    )
    if clock is None:
        return None
    try:
        hour = int(clock[1] or 0)
        if clock[4]:
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if clock[4].upper() == "PM" else 0)
        return datetime(
            int(english[3]),
            months.index(month[:3].lower()) + 1,
            int(day),
            hour,
            int(clock[2] or 0),
            int(clock[3] or 0),
            tzinfo=_date_zone(clock[5] or "", source_zone),
        ).astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def material(
    url: str,
    title: str,
    *,
    preserve_fragment: bool = False,
    title_is_text: bool = False,
    **kwargs: Any,
) -> EditorialMaterial:
    normalized = public_url(url, keep_fragment=preserve_fragment)
    identity = f"url:{normalized}"
    if len(identity) > 512:
        identity = f"url-sha256:{fingerprint(normalized).hex()}"
    identity = kwargs.pop("identity_key", identity)
    kwargs.setdefault("content_format", "html" if kwargs.get("body_html") else "text")
    return EditorialMaterial(
        url=normalized,
        identity_key=identity,
        title=collapse(title if title_is_text else plain(title))[:2000],
        **kwargs,
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
