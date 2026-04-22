from __future__ import annotations

import unittest
from datetime import UTC, datetime

from backend.core.application import HotspotDiscoveryService
from backend.core.domain import AccessMethod, SourceConfig, SourceType
from backend.core.infrastructure import InMemorySourceConfigRepository


class HotspotDiscoveryServiceTestCase(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
