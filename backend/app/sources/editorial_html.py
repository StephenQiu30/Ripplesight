"""Bounded original HTML representation shared by collectors and content admission."""

from __future__ import annotations

import contextlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sources.editorial_schemas import public_url


def safe_srcset(value: str, base: str) -> tuple[tuple[str, str], ...]:
    candidates = []
    parts = value.split(",")
    if len(parts) > 16 or len(value) > 32768:
        return ()
    for part in parts:
        fields = part.strip().split()
        if not 1 <= len(fields) <= 2:
            continue
        descriptor = fields[1] if len(fields) == 2 else ""
        if descriptor and not re.fullmatch(
            r"(?:[1-9]\d{0,4}w|(?:[1-9]\d?|0\.\d{1,2}|[1-9]\.\d{1,2})x)", descriptor
        ):
            continue
        with contextlib.suppress(ValueError):
            candidates.append((public_url(urljoin(base, fields[0])), descriptor))
    return tuple(candidates)


def sanitize_editorial_html(value: str, base: str) -> str:
    if len(value) > 500_000:
        raise ValueError("source HTML exceeds its limit")
    soup = BeautifulSoup(value, "html.parser")
    for node in soup.select(
        "script,style,iframe,object,embed,form,button,input,svg,math,link,meta,base,template"
    ):
        node.decompose()
    for node in soup.find_all(True):
        attrs: dict[str, str] = {}
        for key in ("href", "src", "poster"):
            raw = node.attrs.get(key)
            if isinstance(raw, str):
                with contextlib.suppress(ValueError):
                    attrs[key] = public_url(urljoin(base, raw), keep_fragment=key == "href")
        for key in ("alt", "title"):
            raw = node.attrs.get(key)
            if isinstance(raw, str):
                attrs[key] = raw[:512]
        identity = node.attrs.get("id")
        if (
            isinstance(identity, str)
            and len(identity) <= 128
            and re.fullmatch(r"[\w:.\-]+", identity)
        ):
            attrs["id"] = identity
        for key in ("colspan", "rowspan", "width", "height"):
            raw = node.attrs.get(key)
            if isinstance(raw, str) and raw.isascii() and raw.isdigit() and 1 <= int(raw) <= 4096:
                attrs[key] = str(int(raw))
        classes = node.attrs.get("class")
        if node.name in ("pre", "code") and isinstance(classes, list):
            safe = [
                str(item)
                for item in classes
                if re.fullmatch(r"language-[A-Za-z0-9_+\-]{1,48}", str(item))
            ]
            if safe:
                attrs["class"] = " ".join(safe[:4])
        if node.name in ("video", "audio"):
            for key in ("controls", "muted", "loop"):
                if key in node.attrs:
                    attrs[key] = ""
            if node.attrs.get("preload") in ("none", "metadata"):
                attrs["preload"] = str(node.attrs["preload"])
        if node.name in ("img", "source") and isinstance(node.attrs.get("srcset"), str):
            candidates = safe_srcset(str(node.attrs["srcset"]), base)
            if candidates:
                attrs["srcset"] = ", ".join(f"{url} {size}".strip() for url, size in candidates)
        if node.name == "a" and node.attrs.get("target") == "_blank":
            attrs.update(target="_blank", rel="noopener noreferrer")
        node.attrs.clear()
        node.attrs.update(attrs)
    rendered = str(soup)
    if len(rendered) > 500_000:
        raise ValueError("normalized source HTML exceeds its limit")
    return rendered
