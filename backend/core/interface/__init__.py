"""Interface layer for DTOs, error envelopes, and boundary contracts."""
from .pagination import EventListQuery, PageMeta, PaginatedResult, SearchQuery, SourceListQuery

__all__ = [
    "EventListQuery",
    "PageMeta",
    "PaginatedResult",
    "SearchQuery",
    "SourceListQuery",
]
