from collections.abc import Mapping

from jobs.schemas import (
    JobScopeValue,
    KeywordCollectionSnapshot,
    KeywordQueryAdmissionView,
    KeywordQueryPlanView,
    QuerySourceSkipReason,
)

QUERY_PLAN_SCOPE_KEY = "query_plan"


def build_keyword_query_plan(
    queries: tuple[str, ...],
    *,
    max_queries: int | None,
    skip_reason: QuerySourceSkipReason | None = None,
    collection: KeywordCollectionSnapshot | None = None,
    topic_version: int | None = None,
) -> KeywordQueryPlanView:
    """Describe admission only; this never submits work or claims collection success."""
    if skip_reason is None and max_queries is None:
        raise ValueError("admitted queries require a frozen source limit")
    return KeywordQueryPlanView(
        max_queries=max_queries,
        topic_version=topic_version,
        collection=collection,
        queries=tuple(
            KeywordQueryAdmissionView(
                query_index=index,
                query=query,
                admitted=skip_reason is None and max_queries is not None and index < max_queries,
                skip_reason=skip_reason
                if skip_reason is not None
                else ("query_limit" if max_queries is not None and index >= max_queries else None),
            )
            for index, query in enumerate(queries)
        ),
    )


def read_keyword_query_plan(scope: Mapping[str, JobScopeValue]) -> KeywordQueryPlanView | None:
    value = scope.get(QUERY_PLAN_SCOPE_KEY)
    if value is None:
        return None  # Old jobs have no evidence of queries omitted at admission.
    if not isinstance(value, str):
        raise ValueError("query plan snapshot must be JSON text")
    return KeywordQueryPlanView.model_validate_json(value)


def require_planned_keyword_query(scope: Mapping[str, JobScopeValue]) -> None:
    plan = read_keyword_query_plan(scope)
    if plan is not None and not any(
        item.admitted and item.query == scope.get("query") for item in plan.queries
    ):
        raise ValueError("search query was not admitted by its frozen query plan")
