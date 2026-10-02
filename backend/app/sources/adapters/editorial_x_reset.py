"""Official search DTO bridge used by the fixed-author announcement domain."""

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime

from sources.adapters.editorial_http import EditorialHttpClient
from sources.adapters.editorial_x import OfficialEditorialXClient
from sources.contracts import (
    SearchRequest,
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourcePost,
    SourceStopReason,
)


class OfficialXResetSearchSource:
    def __init__(
        self,
        client: OfficialEditorialXClient,
        http: EditorialHttpClient,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client, self._http, self._clock = client, http, clock

    def fetch_page(self, request: SearchRequest) -> SourcePage:
        if request.source_key != "x":
            raise ValueError("official announcement source must be X")
        page = self._client.search(
            request.query,
            next_token=request.page_token,
            starts_at=request.starts_at,
            ends_at=request.ends_at,
        )
        posts = []
        for m in page.materials:
            raw_references = m.metadata.get("references", [])
            references: Iterable[object] = (
                raw_references if isinstance(raw_references, list) else []
            )

            def reference(kind: str, current: Iterable[object] = references) -> str | None:
                return next(
                    (
                        str(r["id"])
                        for r in current
                        if isinstance(r, Mapping) and r.get("type") == kind
                    ),
                    None,
                )

            raw_metrics = m.metadata.get("public_metrics", {})
            metrics: Mapping[str, object] = raw_metrics if isinstance(raw_metrics, dict) else {}

            def count(key: str, current: Mapping[str, object] = metrics) -> int | None:
                value = current.get(key)
                return value if isinstance(value, int) and not isinstance(value, bool) else None

            author_id = m.metadata.get("author_external_id")
            posts.append(
                SourcePost(
                    source_key="x",
                    external_id=m.external_id or "",
                    identity_basis="guid",
                    author_external_id=str(author_id) if author_id else None,
                    published_at=m.published_at,
                    text=m.body_text or m.excerpt,
                    language=m.language,
                    like_count=count("like_count"),
                    comment_count=count("reply_count"),
                    repost_count=count("retweet_count"),
                    canonical_url=m.url,
                    parent_external_id=reference("replied_to"),
                    quote_external_id=reference("quoted"),
                    text_scope="full" if m.body_status == "ok" else "truncated",
                    title=m.title,
                    author_name=m.author,
                )
            )
        state = (
            SourcePageState.MORE
            if page.next_token
            else SourcePageState.COMPLETE
            if posts
            else SourcePageState.EMPTY
        )
        return SourcePage(
            source_key="x",
            capability=SourceCapability.SEARCH,
            state=state,
            items=tuple(posts),
            next_page_token=page.next_token,
            watermark=None,
            stop_reason=None
            if page.next_token
            else SourceStopReason.END_OF_RESULTS
            if posts
            else SourceStopReason.SOURCE_EMPTY,
            observed_at=self._clock(),
            request_count=self._client.request_count,
            adapter_version="official-x-editorial-v1",
        )

    def close(self) -> None:
        self._http.close()
