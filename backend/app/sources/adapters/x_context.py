"""Bounded official lookup context DTOs; the consumer owns persistence and translation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import Field

from sources.adapters.editorial_x import OfficialEditorialXClient
from sources.contracts import SourcePost
from sources.editorial_schemas import EditorialContract


class XContextPost(EditorialContract):
    id: str = Field(pattern=r"^[0-9]{1,19}$")
    author: str = Field(min_length=1, max_length=128)
    relation: Literal["reply", "quote"]
    original_text: str = Field(min_length=1, max_length=100000)
    published_at: datetime | None = None
    url: str = Field(max_length=2048)


class OfficialXContextReader:
    def __init__(self, client: OfficialEditorialXClient) -> None:
        self._client = client

    def read_context(
        self, post: SourcePost, *, max_reply_depth: int = 2
    ) -> tuple[XContextPost, ...]:
        if not 0 <= max_reply_depth <= 2:
            raise ValueError("reply context is bounded at two levels")
        pending: list[tuple[str, Literal["reply", "quote"], int]] = []
        if post.parent_external_id and max_reply_depth:
            pending.append((post.parent_external_id, "reply", 1))
        if post.quote_external_id:
            pending.append((post.quote_external_id, "quote", 1))
        seen = {post.external_id}
        out: list[XContextPost] = []
        while pending and len(out) < 4:
            id, relation, depth = pending.pop(0)
            if id in seen:
                continue
            seen.add(id)
            page = self._client.lookup(id)
            if not page.materials:
                continue
            material = page.materials[0]
            out.append(
                XContextPost(
                    id=id,
                    author=material.author or "Unknown source author",
                    relation=relation,
                    original_text=material.body_text or material.excerpt or material.title,
                    published_at=material.published_at,
                    url=material.url,
                )
            )
            refs = material.metadata.get("references", [])
            for ref in refs if isinstance(refs, list) else []:
                if not isinstance(ref, Mapping) or not isinstance(ref.get("id"), str):
                    continue
                kind: Literal["reply", "quote"] | None = (
                    "reply"
                    if ref.get("type") == "replied_to"
                    else "quote"
                    if ref.get("type") == "quoted"
                    else None
                )
                if kind and depth < (max_reply_depth if kind == "reply" else 2):
                    pending.append((str(ref["id"]), kind, depth + 1))
        return tuple(out)
