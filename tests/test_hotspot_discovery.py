from __future__ import annotations

import unittest
from datetime import UTC, datetime
from collections.abc import Iterable, Iterator

from backend.core.application import HotspotDiscoveryService
from backend.core.domain import AccessMethod, SourceConfig, SourceType
from backend.core.infrastructure import InMemoryRawContentItemRepository, InMemorySourceConfigRepository


class HotspotDiscoveryServiceTestCase(unittest.TestCase):
    def test_collect_raw_items_only_keeps_enabled_sources(self) -> None:
        source_configs = [
            SourceConfig(
                id="news-main",
                name="News Main",
                source_type=SourceType.NEWS,
                access_method=AccessMethod.API,
                language="en",
                region="global",
                weight=1.3,
                poll_interval_minutes=30,
                enabled=True,
            ),
            SourceConfig(
                id="x-main",
                name="X Main",
                source_type=SourceType.X,
                access_method=AccessMethod.API,
                language="en",
                region="global",
                weight=0.8,
                poll_interval_minutes=15,
                enabled=False,
            ),
        ]
        raw_records = {
            "news-main": [
                {
                    "external_id": "news-1",
                    "title": "News only signal",
                    "url": "https://example.com/news/1",
                    "author": "Reporter",
                    "published_at": "2026-04-22T07:00:00+00:00",
                }
            ],
            "x-main": [
                {
                    "external_id": "tweet-1",
                    "title": "X-only rumor",
                    "url": "https://x.com/openai/status/1",
                    "author": "@openai",
                    "published_at": "2026-04-22T07:05:00+00:00",
                }
            ],
        }
        service = HotspotDiscoveryService(
            source_repository=InMemorySourceConfigRepository(source_configs),
        )

        raw_items = service.collect_raw_items(raw_records, ingested_at=datetime(2026, 4, 22, 8, 0, tzinfo=UTC))

        self.assertEqual(1, len(raw_items))
        self.assertEqual("news-main:news-1", raw_items[0].id)
        self.assertEqual("news-main", raw_items[0].source_config_id)

    def test_collect_raw_items_continues_when_a_source_fails(self) -> None:
        class FailingSourceRecords:
            def __iter__(self) -> Iterator[dict[str, object]]:
                raise RuntimeError("collect failed")

        service = HotspotDiscoveryService(
            source_repository=InMemorySourceConfigRepository(
                [
                    SourceConfig(
                        id="news-main",
                        name="News Main",
                        source_type=SourceType.NEWS,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=1.3,
                        poll_interval_minutes=30,
                        enabled=True,
                    )
                ]
            )
        )
        raw_records: dict[str, list[dict[str, object]] | Iterable[dict[str, object]]] = {
            "news-main": FailingSourceRecords(),
            "missing-source": [
                {
                    "external_id": "x",
                    "title": "ignore",
                    "url": "https://example.com/ignore",
                    "published_at": "2026-04-22T07:00:00+00:00",
                }
            ],
        }

        # Should not fail the whole discovery run, and should return empty for this dataset
        raw_items = service.collect_raw_items(raw_records, ingested_at=datetime(2026, 4, 22, 8, 0, tzinfo=UTC))

        self.assertEqual([], raw_items)

    def test_collect_raw_items_persists_evidence_records(self) -> None:
        raw_content_repository = InMemoryRawContentItemRepository()
        service = HotspotDiscoveryService(
            source_repository=InMemorySourceConfigRepository(
                [
                    SourceConfig(
                        id="news-main",
                        name="News Main",
                        source_type=SourceType.NEWS,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=1.3,
                        poll_interval_minutes=30,
                        enabled=True,
                    )
                ]
            ),
            raw_content_repository=raw_content_repository,
        )
        service.collect_raw_items(
            {
                "news-main": [
                    {
                        "external_id": "news-2",
                        "title": "Persist me",
                        "url": "https://example.com/news/2",
                        "published_at": "2026-04-22T07:20:00+00:00",
                    }
                ]
            },
            ingested_at=datetime(2026, 4, 22, 8, 0, tzinfo=UTC),
        )

        persisted = raw_content_repository.list_all()

        self.assertEqual(1, len(persisted))
        self.assertEqual("news-main:news-2", persisted[0].id)

    def test_normalizes_and_clusters_duplicate_signals(self) -> None:
        service = HotspotDiscoveryService(
            source_repository=InMemorySourceConfigRepository(
                [
                    SourceConfig(
                        id="news-main",
                        name="News Main",
                        source_type=SourceType.NEWS,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=1.3,
                        poll_interval_minutes=30,
                    ),
                    SourceConfig(
                        id="x-main",
                        name="X Main",
                        source_type=SourceType.X,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=0.8,
                        poll_interval_minutes=15,
                    ),
                ]
            )
        )
        ingested_at = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)

        mixed_items = service.normalize_items(
            "news-main",
            [
                {
                    "external_id": "news-1",
                    "title": "OpenAI releases a new reasoning model",
                    "url": "https://example.com/news/openai-reasoning",
                    "author": "Reporter",
                    "published_at": "2026-04-22T07:00:00+00:00",
                }
            ],
            ingested_at=ingested_at,
        ) + service.normalize_items(
            "x-main",
            [
                {
                    "external_id": "tweet-1",
                    "title": "OpenAI releases a new reasoning model",
                    "url": "https://x.com/openai/status/1",
                    "author": "@openai",
                    "published_at": "2026-04-22T07:05:00+00:00",
                },
                {
                    "external_id": "tweet-2",
                    "title": "Another rumor is spreading on X",
                    "url": "https://x.com/noise/status/2",
                    "author": "@noise",
                    "published_at": "2026-04-22T07:10:00+00:00",
                },
            ],
            ingested_at=ingested_at,
        )

        events = service.build_hotspot_events(mixed_items)

        self.assertEqual(2, len(events))
        self.assertEqual("OpenAI releases a new reasoning model", events[0].event_title)
        self.assertEqual(2, len(events[0].evidence_links))
        self.assertGreater(events[0].score, events[1].score)
        self.assertEqual((SourceType.X,), events[1].source_types)
        self.assertLessEqual(events[1].score, 0.9)

    def test_cluster_by_fuzzy_title_similarity(self) -> None:
        service = HotspotDiscoveryService(
            source_repository=InMemorySourceConfigRepository(
                [
                    SourceConfig(
                        id="news-main",
                        name="News Main",
                        source_type=SourceType.NEWS,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=1.3,
                        poll_interval_minutes=30,
                    ),
                    SourceConfig(
                        id="x-main",
                        name="X Main",
                        source_type=SourceType.X,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=0.8,
                        poll_interval_minutes=15,
                    ),
                ]
            )
        )
        ingested_at = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)
        mixed_items = service.normalize_items(
            "news-main",
            [
                {
                    "external_id": "news-3",
                    "title": "OpenAI launches a new reasoning model today",
                    "url": "https://example.com/news/openai-reasoning",
                    "author": "Reporter",
                    "published_at": "2026-04-22T07:00:00+00:00",
                }
            ],
            ingested_at=ingested_at,
        ) + service.normalize_items(
            "x-main",
            [
                {
                    "external_id": "tweet-3",
                    "title": "OpenAI launches new reasoning model today",
                    "url": "https://x.com/openai/status/3",
                    "author": "@openai",
                    "published_at": "2026-04-22T07:05:00+00:00",
                }
            ],
            ingested_at=ingested_at,
        )

        events = service.build_hotspot_events(mixed_items)

        self.assertEqual(1, len(events))
        self.assertEqual((SourceType.NEWS, SourceType.X), events[0].source_types)

    def test_cross_source_event_scores_higher_than_x_noise(self) -> None:
        service = HotspotDiscoveryService(
            source_repository=InMemorySourceConfigRepository(
                [
                    SourceConfig(
                        id="news-main",
                        name="News Main",
                        source_type=SourceType.NEWS,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=1.3,
                        poll_interval_minutes=30,
                    ),
                    SourceConfig(
                        id="x-main",
                        name="X Main",
                        source_type=SourceType.X,
                        access_method=AccessMethod.API,
                        language="en",
                        region="global",
                        weight=0.8,
                        poll_interval_minutes=15,
                    ),
                ]
            )
        )
        ingested_at = datetime(2026, 4, 22, 8, 0, tzinfo=UTC)
        mixed_items = service.normalize_items(
            "news-main",
            [
                {
                    "external_id": "news-4",
                    "title": "OpenAI ships new multimodal toolkit",
                    "url": "https://example.com/news/toolkit",
                    "author": "Reporter",
                    "published_at": "2026-04-22T07:00:00+00:00",
                }
            ],
            ingested_at=ingested_at,
        ) + service.normalize_items(
            "x-main",
            [
                {
                    "external_id": "tweet-4",
                    "title": "OpenAI ships new multimodal toolkit",
                    "author": "@openai",
                    "url": "https://x.com/openai/status/4",
                    "published_at": "2026-04-22T07:10:00+00:00",
                },
                {
                    "external_id": "tweet-noise-1",
                    "title": "Random AI noise from random account",
                    "author": "@random",
                    "url": "https://x.com/noise/status/5",
                    "published_at": "2026-04-22T07:20:00+00:00",
                },
            ],
            ingested_at=ingested_at,
        )

        events = service.build_hotspot_events(mixed_items)

        self.assertEqual(2, len(events))
        self.assertEqual((SourceType.NEWS, SourceType.X), events[0].source_types)
        self.assertEqual((SourceType.X,), events[1].source_types)
        self.assertGreater(events[0].score, events[1].score)
        self.assertLess(events[1].score, 0.9)


if __name__ == "__main__":
    unittest.main()
