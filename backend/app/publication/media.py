"""Local presentation planning; external media is linked unless an owned asset exists."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Literal

from markdown_it import MarkdownIt

from analysis.editorial_translation import Node, parse_body
from publication.exports import safe_link
from publication.schemas import PublicMediaView, PublicOutlineEntry


def body_presentation(
    body: str,
    *,
    body_format: Literal["text", "html", "markdown"] = "text",
    mirrored: dict[str, PublicMediaView] | None = None,
    media: Sequence[PublicMediaView] = (),
) -> tuple[str, list[PublicOutlineEntry], list[PublicMediaView]]:
    if body_format == "text":
        root = Node(
            tag=None, attributes={}, children=[Node(tag="p", attributes={}, children=[body])]
        )
    else:
        html = MarkdownIt("js-default").render(body) if body_format == "markdown" else body
        try:
            root = parse_body(html)
        except ValueError:
            root = Node(
                tag=None, attributes={}, children=[Node(tag="p", attributes={}, children=[body])]
            )
    outline: list[PublicOutlineEntry] = []
    found_media: list[PublicMediaView] = []
    seen_media = set()

    def visit(node: Node) -> None:
        if node.tag in {"h2", "h3", "h4", "h5"}:
            title = node.text().strip()
            if title:
                identity = (
                    f"section-{len(outline) + 1}-{hashlib.sha256(title.encode()).hexdigest()[:8]}"
                )
                node.attributes["id"] = identity
                outline.append(PublicOutlineEntry(id=identity, title=title, level=int(node.tag[1])))
        for index, child in enumerate(node.children):
            if not isinstance(child, Node):
                continue
            if child.tag in {"img", "video", "source"}:
                url = safe_link(child.attributes.get("src", ""))
                if child.tag == "video" and not url:
                    url = next(
                        (
                            safe_link(source.attributes.get("src", ""))
                            for source in child.children
                            if isinstance(source, Node)
                            and source.tag == "source"
                            and safe_link(source.attributes.get("src", ""))
                        ),
                        "",
                    )
                kind = "image" if child.tag == "img" else "video"
                if url and url not in seen_media:
                    seen_media.add(url)
                    found_media.append(
                        PublicMediaView(
                            key=hashlib.sha256(url.encode()).hexdigest()[:24],
                            kind=kind,
                            original_url=url,
                            alt=child.attributes.get("alt")
                            or ("图片" if kind == "image" else "视频"),
                            reading_url=None,
                            state="original_link",
                        )
                    )
                identity = hashlib.sha256(url.encode()).hexdigest()[:24] if url else ""
                saved = (mirrored or {}).get(identity)
                if saved and saved.original_url == url and saved.kind == kind:
                    found_media[:] = [
                        saved if item.key == identity else item for item in found_media
                    ]
                    if saved.state == "available" and saved.reading_url:
                        attributes = {"src": saved.reading_url}
                        if kind == "image":
                            attributes.update({"alt": saved.alt, "loading": "lazy"})
                            if saved.width and saved.height:
                                attributes.update(
                                    {"width": str(saved.width), "height": str(saved.height)}
                                )
                            responsive = [
                                item
                                for item in saved.renditions
                                if item.mode in {"image-720", "image-1200", "image-1600"}
                                and item.width
                            ]
                            if responsive:
                                unique = {item.width: item.reading_url for item in responsive}
                                attributes["srcset"] = ", ".join(
                                    f"{link} {width}w" for width, link in sorted(unique.items())
                                )
                                attributes["sizes"] = "(max-width: 720px) 100vw, 720px"
                        else:
                            attributes.update({"controls": "", "preload": "metadata"})
                        node.children[index] = Node(
                            tag="img" if kind == "image" else "video",
                            attributes=attributes,
                            children=[],
                        )
                        continue
                node.children[index] = Node(
                    tag="a",
                    attributes={"href": url} if url else {},
                    children=[
                        child.attributes.get("alt")
                        or ("查看来源图片" if kind == "image" else "查看来源视频")
                    ],
                )
            else:
                visit(child)

    visit(root)
    for item in media:
        url = safe_link(item.original_url)
        if not url or url in seen_media:
            continue
        seen_media.add(url)
        saved = (mirrored or {}).get(item.key)
        current = saved if saved and saved.original_url == url and saved.kind == item.kind else item
        found_media.append(current)
        if (
            current.state == "available"
            and current.reading_url
            and current.kind in {"image", "video"}
        ):
            attributes = {"src": current.reading_url}
            if current.kind == "image":
                attributes.update({"alt": current.alt, "loading": "lazy"})
                if current.width and current.height:
                    attributes.update({"width": str(current.width), "height": str(current.height)})
            else:
                attributes.update({"controls": "", "preload": "metadata"})
            root.children.append(
                Node(
                    tag="img" if current.kind == "image" else "video",
                    attributes=attributes,
                    children=[],
                )
            )
        else:
            root.children.append(
                Node(
                    tag="p",
                    attributes={},
                    children=[Node(tag="a", attributes={"href": url}, children=[current.alt])],
                )
            )
    return root.render(), outline, found_media
