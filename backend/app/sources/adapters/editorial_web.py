"""HTML/Markdown/changelog/site-specific port of AIHOT web-list.ts (MIT)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from sources.adapters.editorial_parsing import (
    collapse,
    material,
    parse_loose_date,
    sanitize_html,
)
from sources.editorial_schemas import EditorialMaterial, EditorialSourceConfiguration, public_url


def allowed(url: str, config: EditorialSourceConfiguration) -> bool:
    target = re.sub(r"^http://", "https://", url, flags=re.IGNORECASE)

    def convert(value: str) -> str:
        return re.sub(r"^http://", "https://", value, flags=re.IGNORECASE)

    return not any(target.startswith(convert(value)) for value in config.deny_url_prefixes) and (
        not config.allow_url_prefixes
        or any(target.startswith(convert(value)) for value in config.allow_url_prefixes)
    )


def _listing_identity(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(public_url(url))
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query)
            if key.casefold()
            not in {
                "page",
                "paged",
                "cat",
                "category",
                "categories",
                "tag",
                "tags",
                "label",
                "labels",
                "author",
                "authors",
            }
        ]
    )
    return parsed.netloc, parsed.path.rstrip("/"), query


def _navigation(url: str, listing: str, *, preserve_fragment: bool) -> bool:
    if _listing_identity(url) == _listing_identity(listing):
        return not (preserve_fragment and urlsplit(url).fragment)
    return bool(
        re.search(
            (
                "/(?:labels?|tags?|categor(?:y|ies)|authors?|page)(?:/|$)|/(?:19|2"
                "0)\\d{2}(?:/\\d{1,2})?/?$"
            ),
            urlsplit(url).path,
            re.IGNORECASE,
        )
    )


def _absolute(href: str, base: str, config: EditorialSourceConfiguration) -> str | None:
    try:
        joined = urljoin(base, href)
        if (
            joined.startswith("http:")
            and base.startswith("https:")
            and urlsplit(joined).netloc == urlsplit(base).netloc
        ):
            joined = "https:" + joined[5:]
        return public_url(joined, keep_fragment=config.preserve_url_fragment)
    except ValueError:
        return None


def _select(node: Tag, selector: str | None) -> Tag | None:
    if not selector:
        return None
    if node.parent and node in node.parent.select(selector):
        return node
    return node.select_one(selector)


def _regex_capture(pattern: str | None, text: str) -> str | None:
    if not pattern:
        return None
    # Source patterns operate on bounded lines, never an unbounded full response.
    for line in text[:200_000].splitlines()[:1000]:
        match = re.search(pattern, line[:1024])
        if match:
            return match[1] if match.lastindex else match[0]
    return None


def _markdown(
    text: str, base: str, config: EditorialSourceConfiguration
) -> tuple[EditorialMaterial, ...]:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    out: list[EditorialMaterial] = []
    seen = set()
    for match in re.finditer(
        r'\[([^\]]{6,1000})\]\((https?://[^)\s]+|/[^)\s]*)(?:\s+"([^"]*)")?\)', text
    ):
        prefix = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
        if config.links_start_line and not re.fullmatch(
            r"[\s>#*+_|-]*(?:\d+[.)]\s*)?[\s*_]*", prefix
        ):
            continue
        url = _absolute(match[2], base, config)
        if (
            not url
            or url in seen
            or not allowed(url, config)
            or _navigation(url, config.url or base, preserve_fragment=config.preserve_url_fragment)
        ):
            continue
        label = collapse(re.sub(r"[*_`#]", "", match[1]))
        attr = collapse(match[3] or "")
        title = attr if len(attr) >= 6 and attr in label else label
        if len(title) < 6:
            continue
        out.append(material(url, title, preserve_fragment=config.preserve_url_fragment))
        seen.add(url)
        if len(out) >= 1000:
            break
    return tuple(out)


def _html(
    text: str, base: str, config: EditorialSourceConfiguration
) -> tuple[EditorialMaterial, ...]:
    soup = BeautifulSoup(text, "html.parser")
    out = []
    seen = set()
    for node in soup.select(config.item_selector or "a[href]")[:1000]:
        link = (
            _select(node, config.link_selector)
            if config.link_selector
            else node
            if node.name == "a"
            else node.select_one("a[href]")
        )
        if not link or not isinstance(link.get("href"), str):
            continue
        url = _absolute(str(link["href"]), base, config)
        if (
            not url
            or url in seen
            or not allowed(url, config)
            or _navigation(url, config.url or base, preserve_fragment=config.preserve_url_fragment)
        ):
            continue
        title_node = _select(node, config.title_selector) if config.title_selector else link
        title = collapse(
            title_node.get_text(" ", strip=True) if title_node else str(link.get("title", ""))
        )
        if not title:
            continue
        date_node = _select(node, config.published_at_selector)
        date_text = (
            str(date_node.get("datetime") or date_node.get("title") or date_node.get_text())
            if date_node
            else None
        )
        date = parse_loose_date(date_text, config.published_at_utc_offset)
        if date is None:
            date = parse_loose_date(
                _regex_capture(config.published_at_regex, str(node)), config.published_at_utc_offset
            )
        out.append(
            material(url, title, preserve_fragment=config.preserve_url_fragment, published_at=date)
        )
        seen.add(url)
    return tuple(out)


def _changelog(
    text: str, base: str, config: EditorialSourceConfiguration
) -> tuple[EditorialMaterial, ...]:
    soup = BeautifulSoup(text, "html.parser")
    out = []
    section_date = None
    for head in soup.select("article h2[id], article h3[id], .markdown h2[id], .markdown h3[id]")[
        :1000
    ]:
        title = collapse(head.get_text().replace("\u200b", "").rstrip("#"))
        match = re.fullmatch(
            r"(?:[^\d:\uFF1A]{1,12}[:\uFF1A])?\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", title
        )
        if match:
            section_date = parse_loose_date(
                f"{match[1]}-{int(match[2]):02}-{int(match[3]):02} 00:00",
                config.published_at_utc_offset,
            )
            continue
        if head.name == "h2":
            section_date = None
        parts = []
        for sibling in head.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h2", "h3"}:
                break
            parts.append(str(sibling))
        body, text_body = sanitize_html("".join(parts), base)
        url = base.split("#", 1)[0] + "#" + str(head["id"])
        if not allowed(url.split("#", 1)[0], config) or not text_body:
            continue
        out.append(
            material(
                url,
                title,
                preserve_fragment=True,
                published_at=parse_loose_date(title, config.published_at_utc_offset)
                or section_date
                or parse_loose_date(text_body[:80], config.published_at_utc_offset),
                body_html=body,
                body_text=text_body,
                body_status="ok",
            )
        )
    return tuple(out)


def parse_mimo_script(
    text: str, base: str, config: EditorialSourceConfiguration
) -> tuple[EditorialMaterial, ...]:
    start = text.find('sectionTitle:"Blog"')
    if start < 0:
        raise ValueError("mimo_home missing Blog section")
    end = text.find("sectionTitle:", start + 1)
    section = text[start : end if end >= 0 else None]
    literal = r'"(?:[^"\\]|\\.)*"'
    out = []
    seen = set()
    for match in re.finditer(rf"\{{(?:[^{{}}\"]|{literal})*\}}", section):

        def field(name: str, chunk: str = match[0]) -> str:
            found = re.search(rf"\b{name}:({literal})", chunk)
            if found is None:
                return ""
            value = re.sub(r"\\x([0-9a-f]{2})", r"\\u00\1", found[1], flags=re.IGNORECASE).replace(
                "\\'", "'"
            )
            return collapse(str(json.loads(value)))

        url = _absolute(field("link"), base, config)
        title = field("title")
        if (
            not url
            or not title
            or url in seen
            or not allowed(url, config)
            or _navigation(url, config.url or base, preserve_fragment=False)
        ):
            continue
        desc = field("desc")
        out.append(material(url, title, excerpt=desc if desc != title else None))
        seen.add(url)
    if not out:
        raise ValueError("mimo_home Blog list did not map")
    return tuple(out)


def parse_web_list(
    text: str,
    base: str,
    config: EditorialSourceConfiguration,
    *,
    script_fetcher: Callable[[str], str] | None = None,
) -> tuple[EditorialMaterial, ...]:
    if config.kind != "web_list":
        raise ValueError("web parser requires web_list configuration")
    if config.adapter == "mimo_home":
        if script_fetcher is None:
            raise ValueError("mimo_home needs an admitted script fetcher")
        scripts = BeautifulSoup(text, "html.parser").find_all("script", src=True)
        routes: list[str] = []
        mapping = None
        root = None
        for script in reversed(scripts[-10:]):
            url = _absolute(str(script["src"]), base, config)
            if url is None:
                continue
            js = script_fetcher(url)
            route = re.search(r'\{path:"/",[^{}]*\}', js)
            if route:
                routes = re.findall(r'\.e\("([^"]+)"\)', route[0])
            chunks = re.search(
                r'"(static/js/async/)"\+\w+\+"\."\+\(?\{([^}]*)\}\)?\[\w+\]\+"\.js"', js
            )
            public_path = re.search(r'\b\w+\.p="([^"]*)"', js)
            if chunks and public_path:
                mapping = (chunks[1], dict(re.findall(r'"?(\w+)"?:"(\w+)"', chunks[2])))
                root = urljoin(url, public_path[1])
            if routes and mapping and root:
                break
        if not routes or not mapping or not root:
            raise ValueError("mimo_home route or chunk map missing")
        for chunk in reversed(routes[-10:]):
            if chunk not in mapping[1]:
                continue
            js = script_fetcher(urljoin(root, f"{mapping[0]}{chunk}.{mapping[1][chunk]}.js"))
            if 'sectionTitle:"Blog"' in js:
                return parse_mimo_script(js, base, config)
        raise ValueError("mimo_home Blog chunk missing")
    rows = (
        _markdown(text, base, config)
        if config.parse_mode == "markdown"
        else _changelog(text, base, config)
        if config.parse_mode == "docusaurus_changelog"
        else _html(text, base, config)
    )
    if not rows:
        raise ValueError("web listing did not match configured parsing rules")
    return rows


def parse_detail(text: str, url: str, config: EditorialSourceConfiguration) -> dict[str, object]:
    detail = config.detail
    if detail is None:
        return {}
    soup = BeautifulSoup(text, "html.parser")

    def selected(selector: str | None) -> str | None:
        node = soup.select_one(selector) if selector else None
        return (
            str(node.get("datetime") or node.get("content") or node.get("title") or node.get_text())
            if node
            else None
        )

    date = parse_loose_date(
        selected(detail.published_at_selector), detail.published_at_utc_offset
    ) or parse_loose_date(
        _regex_capture(detail.published_at_regex, text), detail.published_at_utc_offset
    )
    if date is None and not detail.published_at_authoritative:
        meta = soup.select_one(
            'meta[property="article:published_time"],meta[name="pubdate"],meta'
            '[itemprop="datePublished"],time[datetime]'
        )
        if meta:
            date = parse_loose_date(
                str(meta.get("content") or meta.get("datetime") or ""),
                detail.published_at_utc_offset,
            )
        if date is None:
            date = parse_loose_date(
                _regex_capture(r'"datePublished"\s*:\s*"([^"]+)"', text),
                detail.published_at_utc_offset,
            )
    title = (
        _regex_capture(detail.title_regex, text)
        if detail.title_regex
        else selected(detail.title_selector)
    )
    summary = selected(detail.summary_selector)
    result: dict[str, object] = {
        "published_at": date,
        "title": collapse(title) if title else None,
        "excerpt": collapse(summary)[:2000] if summary else None,
    }
    if config.fetch_public_content:
        article = soup.select_one("article,main")
        if article:
            html, body = sanitize_html(str(article), url)
            if body:
                result.update(
                    body_html=html, body_text=body, body_status="ok", content_format="html"
                )
    return result
