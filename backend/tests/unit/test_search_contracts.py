"""Check query explanations against implemented paths and unsafe configurations."""

import pytest

from connections.presets import BILIBILI_CHROME_PRESET, SOURCE_PRESETS
from connections.search_contracts import build_source_search_contract


@pytest.mark.parametrize(
    ("key", "mode", "bounded"),
    [
        ("hackernews", "seed_queries", True),
        ("bilibili", "seed_queries", True),
        ("google_news", "seed_queries", False),
        ("news_search", "seed_queries", False),
        ("rss_36kr", "feed_snapshot", False),
    ],
)
def test_supported_paths_distinguish_seeds_local_boolean_and_missing_language(
    key: str, mode: str, bounded: bool
) -> None:
    preset = BILIBILI_CHROME_PRESET if key == "bilibili" else SOURCE_PRESETS[key]
    result = build_source_search_contract(key, dict(preset.config))
    assert result.basis == "connection"
    assert result.query_mode == mode
    conditions = {item.condition: item for item in result.conditions}
    assert list(conditions) == ["match_any", "match_all", "exclude", "language", "window"]
    assert conditions["match_any"].handling == (
        "upstream_and_local" if mode == "seed_queries" else "local_only"
    )
    assert conditions["match_all"].handling == conditions["exclude"].handling == "local_only"
    assert "AND" in conditions["match_all"].explanation
    assert "NOT" in conditions["exclude"].explanation
    assert conditions["language"].handling == "local_only"
    assert "全部为空" in conditions["language"].explanation
    assert conditions["window"].handling == ("upstream_and_local" if bounded else "local_only")
    assert "时间未知排除" in conditions["window"].explanation
    assert "全文" in result.scope_description or key == "google_news"
    if key == "bilibili":
        assert any("非连续" in item for item in result.limitations)
    if key == "rss_36kr":
        assert "不向上游发送关键词" in result.query_description
    if key == "google_news":
        assert any("不是主题语言" in item for item in result.limitations)


@pytest.mark.parametrize("key", ["hackernews", "google_news", "news_search", "rss_36kr"])
def test_unapplied_presets_are_explicit_and_do_not_impersonate_connection_evidence(
    key: str,
) -> None:
    preset = build_source_search_contract(key, None)
    configured = build_source_search_contract(key, dict(SOURCE_PRESETS[key].config))
    assert preset.basis == "preset"
    assert preset.model_dump(exclude={"basis"}) == configured.model_dump(exclude={"basis"})


@pytest.mark.parametrize(
    ("key", "changes"),
    [
        ("hackernews", {"base_url": "https://hn.algolia.com/other"}),
        ("hackernews", {"allowed_hosts": ["hn.algolia.com", "other.example"]}),
        ("google_news", {"feed_url_template": "https://news.google.com/rss"}),
        ("google_news", {"allowed_hosts": ["news.google.com", "other.example"]}),
        ("news_search", {"engines": ["google"]}),
        ("news_search", {"base_url": "http://127.0.0.1:8888/other"}),
        ("rss_36kr", {"feed_url_template": "http://127.0.0.1:1200/36kr/newsflashes?q={query}"}),
        ("bilibili", {"bilibili_transport": "mediacrawler"}),
        ("bilibili", {"allowed_hosts": []}),
    ],
)
def test_directory_keys_never_override_unsupported_configuration(key: str, changes: dict) -> None:
    preset = BILIBILI_CHROME_PRESET if key == "bilibili" else SOURCE_PRESETS[key]
    config = {**dict(preset.config), **changes}
    result = build_source_search_contract(key, config)
    assert result.basis == "connection"
    assert result.query_mode == "unsupported"
    assert all(item.handling == "unsupported" for item in result.conditions)


@pytest.mark.parametrize("key", ["x", "douyin", "future_source"])
@pytest.mark.parametrize("config", [None, {}, {"base_url": "invalid-private-setting"}])
def test_unimplemented_and_invalid_paths_do_not_claim_support_or_expose_config(
    key: str, config
) -> None:
    result = build_source_search_contract(key, config)
    assert result.query_mode == "unsupported"
    assert all(item.handling == "unsupported" for item in result.conditions)
    assert "invalid-private-setting" not in result.model_dump_json()


def test_unapplied_legacy_bilibili_preset_is_fail_closed() -> None:
    result = build_source_search_contract("bilibili", None)
    assert result.basis == "preset" and result.query_mode == "unsupported"
    assert "逐请求暂停保护" in result.query_description
