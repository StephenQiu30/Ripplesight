"""Structure-preserving translation planning; no network, database, or model calls."""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

BATCH_CHARS = 3500
MAX_CHARS = 60000
_BLOCK = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "blockquote",
    "figcaption",
    "td",
    "th",
    "dt",
    "dd",
    "caption",
}
_CONTAINER = _BLOCK | {"ul", "ol", "table", "pre", "figure", "div"}
_INLINE = {"a", "b", "strong", "em", "i", "s", "u", "br", "span", "small", "sup", "sub"}
_MEDIA = {"picture", "video", "audio", "img", "code"}
_ALLOWED = _CONTAINER | _INLINE | _MEDIA | {"thead", "tbody", "tr", "source", "hr"}
_DROP = {"script", "style", "iframe", "object", "embed", "form", "input", "button", "svg", "math"}
_VOID = {"br", "img", "source", "hr"}
_DROP_VOID = {"input", "embed"}
_FOREIGN = re.compile(r"[A-Za-zÀ-ɏЀ-ӿ぀-ヿ]")
_TOKEN = re.compile("\u27e6([0-9]+)\u27e7")


@dataclass
class Node:
    tag: str | None
    attributes: dict[str, str] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)

    def render(self) -> str:
        inner = "".join(
            child.render() if isinstance(child, Node) else html.escape(child)
            for child in self.children
        )
        if self.tag is None:
            return inner
        attributes = "".join(
            f' {key}="{html.escape(value, quote=True)}"' for key, value in self.attributes.items()
        )
        if self.tag in _VOID:
            return f"<{self.tag}{attributes}>"
        return f"<{self.tag}{attributes}>{inner}</{self.tag}>"

    def text(self) -> str:
        return "".join(
            child.text() if isinstance(child, Node) else child for child in self.children
        )


def _safe_url(value: str) -> bool:
    if not value or any(ord(char) < 32 for char in value) or value.startswith("//"):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"http", "https", "mailto"} and not parsed.username and not parsed.password
    ) or (not parsed.scheme and value.startswith(("/", "#")))


def _safe_srcset(value: str) -> bool:
    if not value or len(value) > 8192:
        return False
    for candidate in value.split(","):
        parts = candidate.strip().split()
        if (
            not 1 <= len(parts) <= 2
            or not _safe_url(parts[0])
            or (len(parts) == 2 and re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?[wx]", parts[1]) is None)
        ):
            return False
    return True


class _TreeParser(HTMLParser):
    def __init__(self, *, model_output: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node(None)
        self.stack = [self.root]
        self.drop_depth = 0
        self.nodes = 0
        self.model_output = model_output
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.nodes += 1
        if self.nodes > 10000 or len(self.stack) > 64:
            raise ValueError("HTML structure exceeds translation limits")
        if self.drop_depth:
            if tag not in _VOID:
                self.drop_depth += 1
            return
        if tag in _DROP:
            self.drop_depth = 0 if tag in _DROP_VOID else 1
            self.invalid = self.model_output
            return
        if self.model_output and tag not in _INLINE:
            self.invalid = True
        if tag not in _ALLOWED:
            self.invalid = self.model_output
            return
        safe: dict[str, str] = {}
        for key, value in attrs:
            if value is None:
                if key == "controls" and tag in {"video", "audio"}:
                    safe[key] = ""
                continue
            if self.model_output:
                if tag == "a" and key == "id" and re.fullmatch(r"L[0-9]+", value):
                    safe[key] = value
                else:
                    self.invalid = True
            elif (
                (key in {"href", "src", "poster"} and _safe_url(value))
                or (key == "controls" and tag in {"video", "audio"})
                or (key in {"alt", "title"} and len(value) <= 1000)
                or (key == "id" and re.fullmatch(r"[\w:.-]{1,128}", value))
                or (key in {"width", "height", "colspan", "rowspan"} and value.isdecimal())
                or (key == "srcset" and tag in {"img", "source"} and _safe_srcset(value))
                or (
                    key == "type"
                    and tag == "source"
                    and re.fullmatch(r"(?:image|audio|video)/[A-Za-z0-9.+-]+", value)
                )
            ):
                safe[key] = value
        node = Node(tag, safe)
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.drop_depth:
            self.drop_depth -= 1
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self.stack[-1].children.append(data)


def parse_body(value: str, *, model_output: bool = False) -> Node:
    if len(value) > 1_000_000:
        raise ValueError("body exceeds translation limits")
    parser = _TreeParser(model_output=model_output)
    parser.feed(value)
    parser.close()
    if parser.invalid:
        raise ValueError("translation added unsupported HTML or attributes")
    return parser.root


@dataclass(frozen=True)
class Shielded:
    html: str
    tokens: tuple[Node, ...]
    links: tuple[dict[str, str], ...]


def shield(value: str) -> Shielded:
    if _TOKEN.search(value):
        raise ValueError("body already contains reserved translation placeholders")
    root = parse_body(value)
    tokens: list[Node] = []
    links: list[dict[str, str]] = []

    def visit(node: Node) -> None:
        for index, child in enumerate(node.children):
            if not isinstance(child, Node):
                continue
            if child.tag in _MEDIA:
                tokens.append(child)
                node.children[index] = f"\u27e6{len(tokens) - 1}\u27e7"
                continue
            if child.tag == "a":
                links.append(child.attributes.copy())
                child.attributes = {"id": f"L{len(links) - 1}"}
            visit(child)

    visit(root)
    return Shielded(root.render(), tuple(tokens), tuple(links))


def unshield(answer: str, source: Shielded) -> str | None:
    counts: dict[int, int] = {}
    for match in _TOKEN.finditer(answer):
        key = int(match.group(1))
        counts[key] = counts.get(key, 0) + 1
    if set(counts) != set(range(len(source.tokens))) or any(
        value != 1 for value in counts.values()
    ):
        return None
    try:
        root = parse_body(answer, model_output=True)
    except ValueError:
        return None
    seen: set[int] = set()
    intact = True

    def visit(node: Node) -> None:
        nonlocal intact
        restored: list[Node | str] = []
        for child in node.children:
            if isinstance(child, Node):
                if child.tag == "a":
                    match = re.fullmatch(r"L([0-9]+)", child.attributes.get("id", ""))
                    index = int(match.group(1)) if match else -1
                    if not 0 <= index < len(source.links) or index in seen:
                        intact = False
                    else:
                        seen.add(index)
                        child.attributes = source.links[index].copy()
                visit(child)
                restored.append(child)
            else:
                cursor = 0
                for match in _TOKEN.finditer(child):
                    restored.append(child[cursor : match.start()])
                    restored.append(source.tokens[int(match.group(1))])
                    cursor = match.end()
                restored.append(child[cursor:])
        node.children = restored

    visit(root)
    if not intact or seen != set(range(len(source.links))):
        return None
    return root.render()


@dataclass(frozen=True)
class TranslationPlan:
    source_html: str
    input_fingerprint: str
    parts: tuple[Shielded, ...]
    batches: tuple[tuple[int, ...], ...]
    total_segments: int
    truncated: bool


def _segments(root: Node) -> list[Node]:
    result: list[Node] = []

    def visit(node: Node) -> None:
        for child in node.children:
            if not isinstance(child, Node) or child.tag in {"pre", "code"}:
                continue
            has_block_child = any(
                isinstance(c, Node) and c.tag in _CONTAINER for c in child.children
            )
            if child.tag in _BLOCK and not has_block_child:
                if _FOREIGN.search(child.text()):
                    result.append(child)
            else:
                visit(child)

    visit(root)
    return result


def plan_translation(source_html: str) -> TranslationPlan:
    root = parse_body(source_html)
    blocks = _segments(root)
    parts: list[Shielded] = []
    remaining = MAX_CHARS
    for block in blocks:
        inner = Node(None, children=block.children).render()
        if len(inner) > remaining:
            break
        remaining -= len(inner)
        try:
            parts.append(shield(inner))
        except ValueError:
            break
    batches: list[tuple[int, ...]] = []
    current: list[int] = []
    size = 0
    for index, part in enumerate(parts):
        if current and size + len(part.html) > BATCH_CHARS:
            batches.append(tuple(current))
            current, size = [], 0
        current.append(index)
        size += len(part.html)
    if current:
        batches.append(tuple(current))
    sanitized = root.render()
    fingerprint = hashlib.sha256(
        json.dumps(
            [sanitized, MAX_CHARS, BATCH_CHARS], ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return TranslationPlan(
        sanitized, fingerprint, tuple(parts), tuple(batches), len(blocks), len(parts) != len(blocks)
    )


@dataclass(frozen=True)
class TranslationResult:
    status: str
    html: str
    text: str
    translated_segments: int
    total_segments: int
    complete: bool


def assemble_translation(plan: TranslationPlan, answers: dict[int, str]) -> TranslationResult:
    root = parse_body(plan.source_html)
    blocks = _segments(root)
    done = 0
    for index, part in enumerate(plan.parts):
        restored = unshield(answers[index], part) if index in answers else None
        if restored is not None and restored.strip():
            blocks[index].children = parse_body(restored).children
            done += 1
    complete = done == plan.total_segments and not plan.truncated
    status = "translated" if complete and done else "partial" if done else "skipped"
    return TranslationResult(
        status, root.render(), root.text(), done, plan.total_segments, complete and bool(done)
    )
