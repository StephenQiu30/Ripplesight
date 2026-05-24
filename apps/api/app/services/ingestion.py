from __future__ import annotations

import asyncio

from apps.api.app.models.keyword import Keyword
from apps.api.app.models.source import Source

from apps.api.app.services.providers import Candidate, SourceIngestionError as SourceIngestionError
from apps.api.app.services.providers import build_provider


async def _fetch_candidates_async(source: Source, keyword: Keyword, query: str | None = None) -> list[Candidate]:
    provider = build_provider(source, keyword)
    return await provider.fetch_hot_topics(query=query)


def fetch_candidates(source: Source, keyword: Keyword, query: str | None = None) -> list[Candidate]:
    try:
        return asyncio.run(_fetch_candidates_async(source=source, keyword=keyword, query=query))
    except RuntimeError as exc:
        # In tests and WSGI/legacy sync endpoints this path should not hit a running loop.
        raise SourceIngestionError(f"Failed to fetch candidates from {source.name}: {exc}") from exc
    except SourceIngestionError:
        raise


__all__ = ["Candidate", "SourceIngestionError", "fetch_candidates"]
