from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.core.settings import settings
from apps.api.app.models.hotspot import Hotspot
from apps.api.app.models.keyword import Keyword
from apps.api.app.models.source import Source
from apps.api.app.schemas.search import SearchRead, SearchResultRead
from apps.api.app.services.ai_analysis import analyze_hotspot, expand_keyword_queries
from apps.api.app.services.ingestion import SourceIngestionError, fetch_candidates


def search_sources(session: Session, query: str, source_types: list[str] | None = None, limit: int = 20) -> SearchRead:
    keyword = Keyword(keyword=query, query_template=query, enabled=True)
    sources = _load_search_sources(session, source_types)
    errors: list[str] = []
    items: list[SearchResultRead] = []

    if not sources:
        errors.append("No enabled sources matched the search request.")
        return SearchRead(query=query, items=[], errors=errors)

    for source in sources:
        for expanded_query in expand_keyword_queries(keyword):
            try:
                candidates = fetch_candidates(source, keyword, query=expanded_query)
            except SourceIngestionError as exc:
                errors.append(str(exc))
                continue
            for candidate in candidates:
                hotspot = Hotspot(
                    title=candidate.title,
                    url=candidate.url,
                    source_id=source.id,
                    keyword_id=None,
                    author=candidate.author,
                    snippet=candidate.snippet,
                    published_at=candidate.published_at,
                    raw_payload=candidate.raw_payload,
                )
                analysis = analyze_hotspot(hotspot, keyword)
                status = "active" if analysis.relevance_score >= settings.relevance_threshold else "filtered"
                items.append(
                    SearchResultRead(
                        title=candidate.title,
                        url=candidate.url,
                        source_id=source.id,
                        source_name=source.name,
                        source_type=source.source_type,
                        author=candidate.author,
                        published_at=candidate.published_at,
                        snippet=candidate.snippet,
                        relevance_score=analysis.relevance_score,
                        relevance_reason=analysis.relevance_reason,
                        keyword_mentioned=analysis.keyword_mentioned,
                        importance=analysis.importance,
                        summary=analysis.summary,
                        status=status,
                        raw_payload=candidate.raw_payload,
                    )
                )
                if len(items) >= limit:
                    return SearchRead(query=query, items=_sort_items(items), errors=errors)
    return SearchRead(query=query, items=_sort_items(items)[:limit], errors=errors)


def _load_search_sources(session: Session, source_types: list[str] | None) -> list[Source]:
    stmt = select(Source).where(Source.enabled.is_(True)).order_by(Source.id)
    if source_types:
        normalized = [source_type.lower() for source_type in source_types]
        stmt = stmt.where(Source.source_type.in_(normalized))
    return list(session.scalars(stmt))


def _sort_items(items: list[SearchResultRead]) -> list[SearchResultRead]:
    importance_rank = {"high": 3, "medium": 2, "low": 1}
    return sorted(items, key=lambda item: (importance_rank.get(item.importance, 0), item.relevance_score), reverse=True)
