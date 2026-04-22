from __future__ import annotations

from datetime import UTC, datetime

from backend.core.domain import AccessMethod, KeywordRule, MonitoredAccount, SourceConfig, SourceType


def build_source_configs() -> list[SourceConfig]:
    return [
        SourceConfig(
            id="news-main",
            name="Global AI News",
            source_type=SourceType.NEWS,
            access_method=AccessMethod.API,
            language="en",
            region="global",
            weight=1.4,
            poll_interval_minutes=30,
            enabled=True,
        ),
        SourceConfig(
            id="x-main",
            name="X Signals",
            source_type=SourceType.X,
            access_method=AccessMethod.API,
            language="en",
            region="global",
            weight=0.8,
            poll_interval_minutes=15,
            enabled=True,
        ),
        SourceConfig(
            id="github-main",
            name="GitHub Watch",
            source_type=SourceType.GITHUB,
            access_method=AccessMethod.API,
            language="en",
            region="global",
            weight=1.1,
            poll_interval_minutes=60,
            enabled=False,
        ),
    ]


def build_keyword_rules() -> list[KeywordRule]:
    return [
        KeywordRule(
            id="kw-openai",
            keyword="OpenAI",
            category="company",
            query_template="OpenAI OR GPT OR reasoning model",
            priority=1,
            enabled=True,
        ),
        KeywordRule(
            id="kw-agents",
            keyword="AI agents",
            category="topic",
            query_template="\"AI agents\" OR \"agent framework\"",
            priority=2,
            enabled=True,
        ),
    ]


def build_monitored_accounts() -> list[MonitoredAccount]:
    return [
        MonitoredAccount(
            id="acct-openai",
            platform="x",
            handle="@OpenAI",
            display_name="OpenAI",
            account_type="company",
            weight=1.0,
            enabled=True,
        ),
        MonitoredAccount(
            id="acct-sama",
            platform="x",
            handle="@sama",
            display_name="Sam Altman",
            account_type="founder",
            weight=0.9,
            enabled=True,
        ),
    ]


def build_raw_records() -> dict[str, list[dict[str, object]]]:
    return {
        "news-main": [
            {
                "external_id": "news-1",
                "title": "OpenAI releases a new reasoning model",
                "content_excerpt": "A new reasoning model is released with enterprise positioning.",
                "url": "https://example.com/news/openai-reasoning",
                "author": "Global AI Desk",
                "published_at": "2026-04-22T07:00:00+00:00",
                "language": "en",
            }
        ],
        "x-main": [
            {
                "external_id": "tweet-1",
                "title": "OpenAI releases a new reasoning model",
                "content_excerpt": "Official announcement thread from OpenAI.",
                "url": "https://x.com/openai/status/1",
                "author": "@OpenAI",
                "published_at": "2026-04-22T07:05:00+00:00",
                "language": "en",
            },
            {
                "external_id": "tweet-2",
                "title": "Another rumor is spreading on X",
                "content_excerpt": "Unverified chatter without corroboration from other sources.",
                "url": "https://x.com/noise/status/2",
                "author": "@noise",
                "published_at": "2026-04-22T07:10:00+00:00",
                "language": "en",
            },
        ],
        "github-main": [
            {
                "external_id": "gh-1",
                "title": "OpenAI releases a new reasoning model",
                "content_excerpt": "Related SDK example repository appears shortly after release.",
                "url": "https://github.com/example/openai-reasoning-sdk",
                "author": "example",
                "published_at": "2026-04-22T07:20:00+00:00",
                "language": "en",
            }
        ],
    }


def default_ingested_at() -> datetime:
    return datetime(2026, 4, 22, 8, 0, tzinfo=UTC)
