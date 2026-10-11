from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jobs.schemas import KeywordCollectionSnapshot
from monitors.collection_config import TopicCollectionConfig, language_matches


@pytest.mark.parametrize(
    "language,selected,matched",
    [
        (None, "any", True),
        (None, "en", False),
        ("en-US", "en", True),
        ("ZH_hant", "zh", True),
        ("zh-CN", "en", False),
        ("und", "en", False),
    ],
)
def test_language_uses_declared_primary_tag_only(language, selected, matched):
    assert language_matches(language, selected) is matched


@pytest.mark.parametrize(
    "change",
    [
        {"max_items_per_query": 4},
        {"max_requests_per_query": 4},
        {"starts_at": datetime(2026, 1, 1)},
        {"starts_at": datetime(2025, 12, 31, tzinfo=UTC)},
    ],
)
def test_snapshot_rejects_widened_bounds(change):
    end = datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    values = {
        "topic": TopicCollectionConfig(
            search_window_seconds=600, max_items_per_query=3, max_requests_per_query=3
        ),
        "starts_at": end - timedelta(seconds=600),
        "ends_at": end,
        "max_items_per_query": 3,
        "max_requests_per_query": 3,
    }
    with pytest.raises(ValidationError):
        KeywordCollectionSnapshot(**{**values, **change})


def test_bilibili_one_platform_request_stops_before_search(tmp_path):
    from uuid import uuid4

    import httpx

    from content.schemas import KeywordDiscoveryRunInput
    from sources.adapters.bilibili_chrome import BilibiliChromeAdapter
    from sources.contracts import SearchRequest, SourceSort, SourceStopReason
    from tests.unit.sources.test_keyword_demo import NOW, identity, transport_handler

    requested = []
    charged = []

    def handle(request):
        requested.append((request.url.host, request.url.path))
        return transport_handler(request)

    run = KeywordDiscoveryRunInput(
        run_id=uuid4(),
        configuration_ref=f"topic:{uuid4()}",
        configuration_version=1,
        source_key="bilibili",
        connection_id=uuid4(),
        connection_version=1,
        primary_query="DeepSeek",
        search_sort=SourceSort.LATEST,
        starts_at=NOW - timedelta(seconds=600),
        ends_at=NOW,
        page_size=1,
        latest_max_pages=1,
        latest_max_requests=1,
        top_max_pages=1,
        top_max_requests=1,
        max_seconds=90,
    )
    adapter = BilibiliChromeAdapter(
        identity_env=identity(tmp_path),
        before_request=lambda attempt: charged.append(attempt) is None,
        cancelled=lambda: False,
        max_requests=1,
        max_seconds=90,
        transport=httpx.MockTransport(handle),
    )
    page = adapter.fetch_page(
        SearchRequest(
            source_key="bilibili",
            query=run.primary_query,
            starts_at=run.starts_at,
            ends_at=run.ends_at,
            page_size=1,
        )
    )
    assert charged == [1]
    assert [path for host, path in requested if host == "api.bilibili.com"] == [
        "/x/web-interface/nav"
    ]
    assert page.stop_reason is SourceStopReason.BUDGET_EXHAUSTED
    assert page.request_count == 1


def test_topic_input_preserves_time_and_uuid_json_compatibility():
    from datetime import time
    from uuid import UUID

    from monitors.schemas import MonitorTopicCreateInput

    profile_id = "00000000-0000-0000-0000-000000000001"
    topic = MonitorTopicCreateInput.model_validate(
        {
            "name": "AI",
            "match_any": ["AI"],
            "match_all": [],
            "exclude": [],
            "report_time": "08:00:00",
            "editorial_profile_ids": [profile_id],
            "search_window_seconds": 600,
        }
    )
    assert topic.report_time == time(8)
    assert topic.editorial_profile_ids == [UUID(profile_id)]
