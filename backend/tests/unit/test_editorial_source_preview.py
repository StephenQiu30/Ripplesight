from datetime import UTC, datetime
from uuid import uuid4

from sources.editorial_preview_rules import preview_sample
from sources.editorial_preview_schemas import EditorialSamplePreviewInput


def test_rss_preview_only_returns_twenty_metadata_items_and_never_full_body():
    body = (
        '<rss version="2.0"><channel><title>Controlled feed</title>'
        + "".join(
            f"<item><title>Model {index}</title><link>https://example.com/{index}</link>"
            "<description>" + ("Given local sample only " * 40) + "</description></item>"
            for index in range(25)
        )
        + "</channel></rss>"
    )
    command = EditorialSamplePreviewInput(
        operation_id=uuid4(),
        reason="Local parser preview",
        configuration={
            "kind": "rss",
            "feed_url": "https://example.com/feed",
            "summary_is_body": True,
            "allowed_hosts": ["example.com"],
        },
        sample=body,
    )
    result = preview_sample(command, now=datetime.now(UTC))
    assert result.mode == "sample" and result.status == "complete"
    assert result.count == 25 and len(result.items) == 20 and result.requests == 0
    assert all(len(item.excerpt) <= 200 for item in result.items)
    assert "sample" not in command.model_dump() and "body" not in result.items[0].model_dump()


def test_json_and_web_draft_preview_apply_actual_configuration_filters():
    now = datetime.now(UTC)
    for configuration, sample in (
        (
            {
                "kind": "json_list",
                "url": "https://example.com/items",
                "items_path": "items",
                "title_paths": ["title"],
                "url_template": "https://example.com/{slug}",
            },
            '{"items":[{"title":"New model","slug":"new"}]}',
        ),
        (
            {
                "kind": "web_list",
                "url": "https://example.com/news",
                "item_selector": "article",
                "link_selector": "a",
                "title_selector": "a",
            },
            '<article><a href="/new">New model released</a></article>',
        ),
    ):
        command = EditorialSamplePreviewInput(
            operation_id=uuid4(),
            reason="Given local sample",
            configuration={**configuration, "allowed_hosts": ["example.com"]},
            sample=sample,
        )
        result = preview_sample(command, now=now)
        assert result.count == 1 and result.items[0].url == "https://example.com/new"
