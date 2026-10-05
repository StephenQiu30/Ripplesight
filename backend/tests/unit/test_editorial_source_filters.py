"""Source relevance and excerpt limits use the actual parser/preview/collector path."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape

import httpx
import pytest
from pydantic import ValidationError

from connections.editorial_models import EditorialSourceRun
from connections.editorial_services import EditorialSourceService
from sources.adapters.editorial_json import parse_json_list
from sources.adapters.editorial_parsing import EditorialParsingStats
from sources.adapters.editorial_rss import parse_feed
from sources.editorial_preview_rules import preview_sample
from sources.editorial_preview_schemas import EditorialSamplePreviewInput
from sources.editorial_registry import EditorialSourceRegistry
from sources.editorial_schemas import EditorialCursor, EditorialSourceConfiguration
from tests.unit.test_editorial_sources import NOW, admitted_http, config, profile

_DRAFTS = json.loads(
    (Path(__file__).parents[1] / "fixtures/editorial-source-configuration-drafts.json").read_text()
)


def configuration(kind, **options):
    return config(
        kind,
        **(
            {"feed_url": "https://example.com/feed"}
            if kind == "rss"
            else {
                "url": "https://example.com/list",
                "items_path": "",
                "title_paths": ["title"],
                "summary_paths": ["summary"],
                "url_template": "https://example.com/{id}",
                "published_at_path": "date",
            }
        ),
        **options,
    )


def sample(kind, rows):
    if kind == "json_list":
        return json.dumps(rows)
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        + "".join(
            f'<entry><title type="html">{escape(row["title"])}</title>'
            f'<link href="https://example.com/{row["id"]}"/>'
            f'<summary type="html">{escape(row.get("summary", ""))}</summary>'
            + "".join(f'<category term="{escape(cat)}"/>' for cat in row.get("categories", []))
            + "</entry>"
            for row in rows
        )
        + "</feed>"
    )


def parse(kind, rows, c, *, stats=None):
    text = sample(kind, rows)
    return (
        parse_feed(text, c.feed_url, c, stats=stats)
        if kind == "rss"
        else parse_json_list(text, c, stats=stats)
    )


@pytest.mark.parametrize("kind", ["rss", "json_list"])
@pytest.mark.parametrize(
    ("title", "summary", "terms", "kept"),
    [
        ("New <b>Ai</b> release", "", [" AI "], True),
        (
            "Announcement",
            "<p>ARTIFICIAL\n INTELLIGENCE update</p>",
            ["artificial intelligence"],
            True,
        ),
        ("Announcement", "研究人工智能发展", ["人工智能"], True),
        ("\uff21\uff29 release", "", ["AI"], True),
        ("Announcement", "<script>AI</script>unrelated", ["AI"], False),
        ("said daily email AI2 xAI", "", ["AI"], False),
        ("AI-enabled", "", ["AI"], True),
        ("Learning", "machine learningness", ["machine learning"], False),
        ("Learning", "Machine learning.", ["AI", "machine learning"], True),
        ("Artificial", "intelligence", ["artificial intelligence"], False),
    ],
)
def test_include_matches_normalized_title_or_summary_with_word_boundaries(
    kind, title, summary, terms, kept
):
    c = configuration(kind, require_any_terms=terms)
    stats = EditorialParsingStats()
    rows = parse(kind, [{"id": 1, "title": title, "summary": summary}], c, stats=stats)
    assert bool(rows) is kept
    assert stats.filtered == int(not kept)


@pytest.mark.parametrize("kind", ["rss", "json_list"])
def test_include_precedes_noise_override_and_preserves_url_rejection_and_counts(kind):
    c = configuration(
        kind,
        require_any_terms=["AI"],
        deny_url_prefixes=["https://example.com/4"],
        ingest_noise_filter={"drop_markers": ["spam"], "keep_if_matches": ["release"]},
    )
    rows = [
        {"id": 1, "title": "Unrelated release"},
        {"id": 2, "title": "AI spam"},
        {"id": 3, "title": "AI spam release"},
        {"id": 4, "title": "AI release"},
    ]
    http, _ = admitted_http(lambda request: httpx.Response(200, text=sample(kind, rows)))
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW, source_added_at=NOW)
    try:
        page = registry.collect(profile(c), EditorialCursor(), {})
    finally:
        registry.close()
    assert page.status == "complete" and [row.title for row in page.materials] == [
        "AI spam release"
    ]
    assert page.filtered == 3
    preview = preview_sample(
        EditorialSamplePreviewInput(
            operation_id=uuid4(),
            reason="Controlled sample",
            configuration=c,
            sample=sample(kind, rows),
        ),
        now=NOW,
    )
    assert preview.count == 1 and preview.filtered == 3 and preview.requests == 0


def test_include_and_noise_override_do_not_bypass_category_denial():
    c = configuration(
        "rss",
        require_any_terms=["AI"],
        ingest_noise_filter={"keep_if_matches": ["AI"]},
        deny_categories=["blocked"],
    )
    rows = [{"id": 1, "title": "AI", "categories": ["Blocked"]}]
    http, _ = admitted_http(lambda request: httpx.Response(200, text=sample("rss", rows)))
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW, source_added_at=NOW)
    try:
        page = registry.collect(profile(c), EditorialCursor(initialized_at=NOW), {})
        assert page.status == "complete" and not page.materials and page.filtered == 1
    finally:
        registry.close()


@pytest.mark.parametrize("kind", ["rss", "json_list"])
@pytest.mark.parametrize("limit", [1, 300, 4000])
def test_excerpt_limit_counts_unicode_characters_and_marks_only_actual_truncation(kind, limit):
    c = configuration(kind, summary_max_chars=limit, summary_is_body=True)
    summary = "中😀" * 2100 + "AI"
    row = parse(kind, [{"id": 1, "title": "Source", "summary": summary}], c)[0]
    assert row.excerpt == summary[: limit - 1] + "…" and len(row.excerpt) == limit
    assert row.metadata["summary_truncated"] is True
    assert row.body_text == summary and row.body_status == "ok"
    exact = parse(kind, [{"id": 1, "title": "Source", "summary": "中" * limit}], c)[0]
    assert exact.excerpt == "中" * limit and "summary_truncated" not in exact.metadata
    empty = parse(kind, [{"id": 1, "title": "Source"}], c)[0]
    assert empty.excerpt is None and "summary_truncated" not in empty.metadata


@pytest.mark.parametrize("kind", ["rss", "json_list"])
def test_include_reads_summary_after_excerpt_limit_and_all_filtered_is_visible(kind):
    c = configuration(kind, require_any_terms=["AI"], summary_max_chars=300)
    rows = [{"id": 1, "title": "Source", "summary": "Long source. " * 400 + "AI"}]
    assert len(parse(kind, rows, c)) == 1
    command = EditorialSamplePreviewInput(
        operation_id=uuid4(),
        reason="Controlled sample",
        configuration=c,
        sample=sample(kind, [{"id": 1, "title": "Unrelated", "summary": "said"}]),
    )
    result = preview_sample(command, now=NOW)
    assert result.status == "complete" and result.count == 0 and result.filtered == 1


@pytest.mark.parametrize(("kind", "default_limit"), [("rss", 4000), ("json_list", 2000)])
def test_old_configuration_keeps_original_summary_limit_and_unrelated_items(kind, default_limit):
    c = configuration(kind)
    assert not c.require_any_terms and c.summary_max_chars is None
    row = parse(kind, [{"id": 1, "title": "Unrelated", "summary": "字" * 4100}], c)[0]
    assert row.excerpt == "字" * default_limit and "summary_truncated" not in row.metadata
    assert EditorialSourceConfiguration.model_validate(c.model_dump(mode="json")) == c


@pytest.mark.parametrize(
    "options",
    [
        {"require_any_terms": ["AI"] * 101},
        {"require_any_terms": [""]},
        {"require_any_terms": [" \n "]},
        {"require_any_terms": ["x" * 129]},
        {"require_any_terms": ["㍿" * 33]},
        {"summary_max_chars": 0},
        {"summary_max_chars": 4001},
        {"summary_max_chars": True},
        {"summary_max_chars": 300.5},
    ],
)
def test_configuration_rejects_unbounded_or_invalid_rules(options):
    with pytest.raises(ValidationError):
        configuration("rss", **options)


def test_configuration_limits_are_inclusive_and_other_kinds_are_not_expanded():
    c = configuration("rss", require_any_terms=["x" * 128] * 100, summary_max_chars=4000)
    assert len(c.require_any_terms) == 100
    for field in ({"require_any_terms": ["AI"]}, {"summary_max_chars": 300}):
        with pytest.raises(ValidationError):
            config("web_list", url="https://example.com/list", **field)


def test_github_api_version_header_is_non_secret_bounded_and_drops_prereleases():
    c = configuration(
        "json_list",
        headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        require_boolean={"path": "prerelease", "equals": False},
        summary_max_chars=300,
    )
    stats = EditorialParsingStats()
    rows = parse(
        "json_list",
        [
            {"id": 1, "title": "v1.0", "summary": "release " * 100, "prerelease": False},
            {"id": 2, "title": "v2.0-rc1", "prerelease": True},
            {"id": 3, "title": "Missing flag"},
        ],
        c,
        stats=stats,
    )
    assert len(rows) == 1 and len(rows[0].excerpt) == 300 and stats.filtered == 2
    for header in (
        {"X-GitHub-Api-Version": "x" * 257},
        {"X-GitHub-Api-Version": "2022-11-28\nAuthorization: secret"},
        {"Authorization": "secret"},
    ):
        with pytest.raises(ValidationError):
            configuration("json_list", headers=header)


def test_invalid_materials_are_protocol_errors_and_not_counted_as_filtered():
    c = configuration("json_list", require_any_terms=["AI"])
    stats = EditorialParsingStats()
    with pytest.raises(ValueError, match="did not map"):
        parse_json_list('[{"id":1}]', c, stats=stats)
    assert stats.filtered == 0
    # Legacy conditional parsers still tolerate an unmappable item passing its condition.
    c = configuration("json_list", require_boolean={"path": "valid", "equals": True})
    assert parse_json_list('[{"valid":true}]', c) == ()


@pytest.mark.parametrize("kind", ["rss", "json_list"])
def test_invalid_urls_and_oversized_titles_do_not_become_filtered_items(kind):
    c = configuration(kind, require_any_terms=["AI"])
    stats = EditorialParsingStats()
    if kind == "rss":
        text = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Unrelated</title>'
            '<link href="javascript:invalid"/></entry></feed>'
        )
        with pytest.raises(ValueError, match="did not map"):
            parse_feed(text, c.feed_url, c, stats=stats)
    else:
        c = config(
            "json_list",
            url="https://example.com/list",
            title_paths=["title"],
            url_template="{raw:url}",
            require_any_terms=["AI"],
        )
        with pytest.raises(ValueError, match="did not map"):
            parse_json_list('[{"title":"Unrelated","url":"javascript:invalid"}]', c, stats=stats)
    assert stats.filtered == 0
    # No new fields: the original parser skips a bad title and still admits the next item.
    c = configuration(kind)
    rows = parse(kind, [{"id": 1, "title": "x" * 100_001}, {"id": 2, "title": "Valid"}], c)
    assert [row.title for row in rows] == ["Valid"]


@pytest.mark.parametrize("name", _DRAFTS)
def test_recommended_configuration_drafts_pass_kind_and_field_validation(name):
    c = EditorialSourceConfiguration.model_validate(_DRAFTS[name])
    assert not c.summary_is_body and c.body_extraction is None and c.detail is None
    if name.startswith("github_"):
        text = json.dumps(
            [
                {
                    "id": 1,
                    "name": "v1.0",
                    "html_url": c.allow_url_prefixes[0] + "tag/v1.0",
                    "body": "Release notes. " * 100,
                    "prerelease": False,
                    "draft": False,
                    "author": {"login": "maintainer"},
                    "published_at": "2026-10-05T02:00:00Z",
                },
                {"id": 2, "name": "v2.0-rc1", "prerelease": True},
            ]
        )
        stats = EditorialParsingStats()
        rows = parse_json_list(text, c, stats=stats)
        assert len(rows) == 1 and stats.filtered == 1
        assert len(rows[0].excerpt) == 300 and rows[0].excerpt.endswith("…")
        assert rows[0].published_at == datetime(2026, 10, 5, 2, tzinfo=UTC)
        assert rows[0].external_id == "1" and rows[0].author == "maintainer"
    elif name == "federal_register_ai":
        rows = parse_json_list(
            json.dumps(
                {
                    "results": [
                        {
                            "title": "AI regulation",
                            "abstract": "Artificial intelligence guidance.",
                            "html_url": "https://www.federalregister.gov/documents/2026/10/05/2026-12345/ai",
                            "publication_date": "2026-10-05",
                            "document_number": "2026-12345",
                            "agencies": [{"name": "Controlled agency"}],
                        },
                    ]
                }
            ),
            c,
        )
        assert rows[0].published_at == datetime(2026, 10, 5, tzinfo=UTC)
        assert rows[0].external_id == "2026-12345" and rows[0].author == "Controlled agency"


@pytest.mark.parametrize(
    ("prepared", "expected"),
    [(None, 0), ({"filtered": 3}, 3), ({"_filter_receipt": {"filtered": 3}}, 3)],
)
def test_run_statistics_read_existing_stage_or_terminal_receipt_without_new_columns(
    prepared, expected
):
    run = EditorialSourceRun(
        id=uuid4(),
        status="succeeded",
        configuration_version=1,
        found=1,
        created=1,
        revised=0,
        prepared_page=prepared,
    )
    assert EditorialSourceService._result(run).filtered == expected
