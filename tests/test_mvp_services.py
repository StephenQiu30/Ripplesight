from __future__ import annotations

import unittest

from apps.api.app.core.settings import settings
from apps.api.app.models.ai_analysis import AiAnalysis
from apps.api.app.models.hotspot import Hotspot
from apps.api.app.models.keyword import Keyword
from apps.api.app.models.source import Source
from apps.api.app.services.ai_analysis import analyze_hotspot, expand_keyword_queries
from apps.api.app.services.ingestion import SourceIngestionError, fetch_candidates
from apps.api.app.services.notification import notify_hotspot


class CollectingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)


class SettingsPatchMixin:
    def patch_settings(self, **values: object) -> None:
        originals = {key: getattr(settings, key) for key in values}
        for key, value in values.items():
            setattr(settings, key, value)
        self.addCleanup(lambda: [setattr(settings, key, value) for key, value in originals.items()])


class MvpServiceTests(SettingsPatchMixin, unittest.TestCase):
    def test_fallback_query_expansion_returns_two_to_five_unique_queries(self) -> None:
        self.patch_settings(openai_api_key=None, openai_model=None)
        keyword = Keyword(id=1, keyword="AI agent", query_template=None, enabled=True, priority=0)

        queries = expand_keyword_queries(keyword)

        self.assertGreaterEqual(len(queries), 2)
        self.assertLessEqual(len(queries), 5)
        self.assertEqual(len(queries), len(set(query.lower() for query in queries)))
        self.assertEqual(queries[0], "AI agent")

    def test_fallback_analysis_marks_keyword_mentions_above_threshold(self) -> None:
        self.patch_settings(openai_api_key=None, openai_model=None)
        keyword = Keyword(id=1, keyword="OpenAI", query_template=None, enabled=True, priority=0)
        hotspot = Hotspot(
            id=10,
            title="OpenAI launches new agent tooling",
            url="https://example.com/openai-agent",
            source_id=1,
            keyword_id=1,
            snippet="OpenAI released new tools for agent builders.",
            raw_payload={},
        )

        result = analyze_hotspot(hotspot, keyword)

        self.assertTrue(result.keyword_mentioned)
        self.assertGreaterEqual(result.relevance_score, settings.relevance_threshold)
        self.assertEqual(result.importance, "high")
        self.assertTrue(result.used_fallback)

    def test_fallback_analysis_marks_missing_keyword_below_threshold(self) -> None:
        self.patch_settings(openai_api_key=None, openai_model=None, relevance_threshold=50.0)
        keyword = Keyword(id=1, keyword="OpenAI", query_template=None, enabled=True, priority=0)
        hotspot = Hotspot(
            id=11,
            title="A database release",
            url="https://example.com/database",
            source_id=1,
            keyword_id=1,
            snippet="A database project shipped a maintenance release.",
            raw_payload={},
        )

        result = analyze_hotspot(hotspot, keyword)

        self.assertFalse(result.keyword_mentioned)
        self.assertLess(result.relevance_score, settings.relevance_threshold)
        self.assertEqual(result.importance, "low")

    def test_optional_x_and_bing_sources_skip_without_credentials(self) -> None:
        self.patch_settings(x_api_bearer_token=None, bing_search_api_key=None)
        keyword = Keyword(id=1, keyword="AI", query_template=None, enabled=True, priority=0)
        x_source = Source(id=1, name="X/Twitter", source_type="x_twitter", enabled=True, config={})
        bing_source = Source(id=2, name="Bing", source_type="bing", enabled=True, config={})

        with self.assertRaisesRegex(SourceIngestionError, "X_API_BEARER_TOKEN"):
            fetch_candidates(x_source, keyword)

        with self.assertRaisesRegex(SourceIngestionError, "BING_SEARCH_API_KEY"):
            fetch_candidates(bing_source, keyword)

    def test_smtp_missing_records_skipped_notification(self) -> None:
        self.patch_settings(smtp_host=None, smtp_from_email=None, smtp_to_email=None)
        session = CollectingSession()
        hotspot = Hotspot(id=20, title="OpenAI launch", url="https://example.com/openai", source_id=1, keyword_id=1, raw_payload={})
        analysis = AiAnalysis(
            hotspot_id=20,
            is_real=True,
            relevance_score=80,
            relevance_reason="关键词命中，相关性高。",
            keyword_mentioned=True,
            importance="high",
            summary="OpenAI 发布新产品。",
            model_name="local-fallback",
            raw_response={},
        )

        notification = notify_hotspot(session, hotspot, analysis)  # type: ignore[arg-type]

        self.assertEqual(notification.status, "skipped")
        self.assertEqual(notification.error_message, "SMTP is not configured.")
        self.assertEqual(session.added, [notification])


if __name__ == "__main__":
    unittest.main()
