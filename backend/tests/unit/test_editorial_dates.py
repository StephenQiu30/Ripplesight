"""AIHOT date/Atom regression cases adapted to HotKey's source contracts."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from xml.sax.saxutils import escape

import httpx
import pytest

from sources.adapters.editorial_json import parse_json_list
from sources.adapters.editorial_parsing import material, parse_loose_date
from sources.adapters.editorial_rss import parse_feed
from sources.adapters.editorial_web import parse_detail, parse_web_list
from sources.editorial_registry import EditorialSourceRegistry
from sources.editorial_schemas import EditorialCursor
from tests.unit.test_editorial_sources import NOW, admitted_http, config, profile


@pytest.mark.parametrize("kind", ["rss", "web_list", "json_list"])
def test_first_import_uses_source_creation_48h_and_keeps_limit_only_on_first_run(kind):
    added = NOW - timedelta(days=10)
    cutoff = added - timedelta(hours=48)
    dates = [cutoff - timedelta(seconds=1), cutoff, None, added, NOW]
    if kind == "rss":
        c = config(kind, feed_url="https://example.com/feed", initial_backfill_limit=3)
        text = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            + "".join(
                f'<entry><title>Article {i}</title><link href="https://example.com/{i}"/>'
                + (f"<published>{date.isoformat()}</published>" if date else "")
                + "</entry>"
                for i, date in enumerate(dates)
            )
            + "</feed>"
        )
    elif kind == "web_list":
        c = config(
            kind,
            url="https://example.com/news",
            item_selector="article",
            published_at_selector="time",
            initial_backfill_limit=3,
        )
        text = "".join(
            f'<article><a href="/{i}">Article {i}</a>'
            + (f'<time datetime="{date.isoformat()}"></time>' if date else "")
            + "</article>"
            for i, date in enumerate(dates)
        )
    else:
        c = config(
            kind,
            url="https://example.com/api",
            title_paths=["title"],
            url_template="https://example.com/{id}",
            published_at_path="date",
            initial_backfill_limit=3,
        )
        text = json.dumps(
            [
                {"id": i, "title": f"Article {i}", "date": date.isoformat() if date else None}
                for i, date in enumerate(dates)
            ]
        )
    http, _ = admitted_http(lambda request: httpx.Response(200, text=text))
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW, source_added_at=added)
    try:
        first = registry.collect(profile(c), EditorialCursor(), {})
        assert first.status == "complete"
        assert [row.title for row in first.materials] == ["Article 1", "Article 2", "Article 3"]
        assert first.materials[1].published_at is None
        later = registry.collect(profile(c), first.cursor, {})
        assert later.status == "complete" and len(later.materials) == 5
        assert later.materials[0].published_at == dates[0]
    finally:
        registry.close()


@pytest.mark.parametrize("type_attribute", ["", ' type="text"'])
def test_atom_text_preserves_literal_title_summary_body_and_does_not_make_media(type_attribute):
    title = "<dialog>"
    summary = "Use <model> & keep &lt;literal&gt; unchanged."
    body = (
        summary
        + '\n<script>alert(1)</script><img src="https://example.com/literal.png"> '
        + ("Article text. " * 30)
    )
    text = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        '<link href="https://example.com/post"/>'
        f"<title{type_attribute}>{escape(title)}</title>"
        f"<summary{type_attribute}>{escape(summary)}</summary>"
        f"<content{type_attribute}>{escape(body)}</content></entry></feed>"
    )
    row = parse_feed(
        text, "https://example.com/feed", config("rss", feed_url="https://example.com/feed")
    )[0]
    assert row.title == title and row.excerpt == summary
    assert row.body_text == body.strip() and row.body_status == "ok"
    assert row.content_format == "text" and row.body_html is None and row.media == ()


@pytest.mark.parametrize("host_zone", ["UTC", "Asia/Shanghai", "America/New_York", "Europe/Berlin"])
def test_english_dates_ignore_host_daylight_saving_and_keep_explicit_zones(host_zone):
    original = os.environ.get("TZ")
    try:
        os.environ["TZ"] = host_zone
        time.tzset()
        cases = [
            ("Mar 8, 2026 02:30", "+00:00", "2026-03-08T02:30:00+00:00"),
            ("8 March 2026 02:30:45", "+08:00", "2026-03-07T18:30:45+00:00"),
            ("March 29th, 2026 02:30", "+00:00", "2026-03-29T02:30:00+00:00"),
            ("29 Mar 2026 02:30", "-07:00", "2026-03-29T09:30:00+00:00"),
            ("Sep 26, 2026 10:00 PM", "+08:00", "2026-09-26T14:00:00+00:00"),
            ("Mar 8, 2026 02:30 EST", "+08:00", "2026-03-08T07:30:00+00:00"),
            ("Mar 8, 2026 10:30 PM PDT", "+08:00", "2026-03-09T05:30:00+00:00"),
            ("March 8th, 2026 02:30 +0200", "+08:00", "2026-03-08T00:30:00+00:00"),
            ("Sep 26, 2026 10:00 PM CST", "+08:00", "2026-09-26T14:00:00+00:00"),
        ]
        for value, offset, expected in cases:
            assert parse_loose_date(value, offset) == datetime.fromisoformat(expected)
        for invalid in (
            "Feb 30, 2026 02:30",
            "Mar 8, 2026 25:30 GMT",
            "2026-02-30",
            "v1.2",
            "yesterday",
        ):
            assert parse_loose_date(invalid) is None
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


@pytest.mark.parametrize(
    "unit,good",
    [
        ("iso", "2026-10-02T02:00:00Z"),
        ("epoch_s", NOW.timestamp()),
        ("epoch_ms", NOW.timestamp() * 1000),
        ("yyyymmdd", "20261002"),
    ],
)
def test_json_invalid_middle_dates_are_retained_with_reason_and_later_rows_survive(unit, good):
    c = config(
        "json_list",
        url="https://example.com/api",
        title_paths=["title"],
        url_template="https://example.com/{id}",
        published_at_path="date",
        published_at_unit=unit,
    )
    values = [good, "unknown", {"toString": None}, [{"toString": None}], 1e100, good, None]
    rows = parse_json_list(
        json.dumps(
            [{"id": i, "title": f"Article {i}", "date": value} for i, value in enumerate(values)]
        ),
        c,
    )
    assert len(rows) == len(values)
    assert rows[0].published_at and rows[5].published_at
    for row in rows[1:5]:
        assert row.published_at is None
        assert row.metadata["publication_date_reason"] == "invalid_publication_date"
    assert rows[6].published_at is None and not rows[6].metadata


@pytest.mark.parametrize("offset,hour", [("+08:00", 2), ("-07:00", 17)])
def test_feed_json_web_and_detail_naive_times_share_configured_source_offset(offset, hour):
    expected = datetime(2026, 9, 26, hour, tzinfo=UTC)
    rss = config("rss", feed_url="https://example.com/feed", published_at_utc_offset=offset)
    rows = parse_feed(
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Update</title>'
        '<link href="https://example.com/post"/><published>2026-09-26T10:00:00</published>'
        "<updated>2026-09-26T12:00:00Z</updated></entry></feed>",
        "https://example.com/feed",
        rss,
    )
    assert rows[0].published_at == expected
    assert rows[0].source_updated_at == datetime(2026, 9, 26, 12, tzinfo=UTC)
    js = config(
        "json_list",
        url="https://example.com/api",
        title_paths=["title"],
        url_template="https://example.com/{id}",
        published_at_path="date",
        published_at_utc_offset=offset,
    )
    assert (
        parse_json_list('[{"id":1,"title":"Update","date":"2026-09-26T10:00:00"}]', js)[
            0
        ].published_at
        == expected
    )
    web = config(
        "web_list",
        url="https://example.com/news",
        item_selector="article",
        published_at_selector="time",
        published_at_utc_offset=offset,
        detail={"published_at_selector": "time", "published_at_utc_offset": offset},
    )
    html = (
        '<article><a href="/post">Update</a><time datetime="2026-09-26T10:00:00"></time></article>'
    )
    assert parse_web_list(html, "https://example.com/news", web)[0].published_at == expected
    assert parse_detail(html, "https://example.com/post", web)["published_at"] == expected


def test_default_offset_and_date_only_compatibility():
    assert parse_loose_date("2026-09-26 10:00") == datetime(2026, 9, 26, 2, tzinfo=UTC)
    assert parse_loose_date("2026-09-26") == datetime(2026, 9, 26, tzinfo=UTC)
    assert parse_loose_date("2026-09-26T10:00:00+09:00", "-07:00") == datetime(
        2026, 9, 26, 1, tzinfo=UTC
    )
    assert material("https://example.com/test", "Test").published_at is None


@pytest.mark.parametrize("type_attribute", ["", ' type="text"'])
def test_atom_text_summary_can_be_plain_body_without_html_decoding(type_attribute):
    summary = "Use <model> & keep &lt;literal&gt; unchanged."
    text = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Summary</title>'
        '<link href="https://example.com/post"/>'
        f"<summary{type_attribute}>{escape(summary)}</summary></entry></feed>"
    )
    for summary_is_body in (False, True):
        row = parse_feed(
            text,
            "https://example.com/feed",
            config("rss", feed_url="https://example.com/feed", summary_is_body=summary_is_body),
        )[0]
        assert row.excerpt == summary and row.body_html is None and row.media == ()
        assert row.body_text == (summary if summary_is_body else None)
        assert row.body_status == ("ok" if summary_is_body else "pending")


@pytest.mark.parametrize("kind", ["rss", "web_list", "json_list"])
def test_first_import_rechecks_date_revealed_by_detail_and_never_fetches_known_archive(kind):
    listing = {
        "rss": (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><title>Archive</title><link href="https://example.com/old"/>'
            "<published>2020-01-01T00:00:00Z</published></entry>"
            '<entry><title>No list date</title><link href="https://example.com/unknown"/>'
            "</entry></feed>"
        ),
        "web_list": (
            '<article><a href="/old">Archive</a><time datetime="2020-01-01"></time></article>'
            '<article><a href="/unknown">No list date</a></article>'
        ),
        "json_list": json.dumps(
            [
                {"id": "old", "title": "Archive", "date": "2020-01-01"},
                {"id": "unknown", "title": "No list date"},
            ]
        ),
    }
    options = {
        "rss": {"feed_url": "https://example.com/feed"},
        "web_list": {
            "url": "https://example.com/list",
            "item_selector": "article",
            "published_at_selector": "time",
        },
        "json_list": {
            "url": "https://example.com/list",
            "title_paths": ["title"],
            "url_template": "https://example.com/{id}",
            "published_at_path": "date",
        },
    }
    c = config(kind, **options[kind], detail={"max_fetches": 2, "published_at_selector": "time"})
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(
            200,
            text='<time datetime="2020-01-01"></time>'
            if request.url.path in {"/old", "/unknown"}
            else listing[kind],
        )

    http, _ = admitted_http(handler)
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW, source_added_at=NOW)
    try:
        first = registry.collect(profile(c), EditorialCursor(), {})
        assert first.status == "complete" and not first.materials
        assert requested == (["/feed", "/unknown"] if kind == "rss" else ["/list", "/unknown"])
        later = registry.collect(profile(c), first.cursor, {})
        assert later.status == "complete" and len(later.materials) == 2
    finally:
        registry.close()


@pytest.mark.parametrize(
    "value,offset,expected",
    [
        ("2026/09/26", "+08:00", "2026-09-25T16:00:00+00:00"),
        ("2026年9月26日 10:00", "-07:00", "2026-09-26T17:00:00+00:00"),
        ("Sep 26, 2026", "+08:00", "2026-09-25T16:00:00+00:00"),
        ("Sat, 26 Sep 2026 10:00:00 GMT", "+08:00", "2026-09-26T10:00:00+00:00"),
        ("2026-09-26 10:00:00 GMT", "+08:00", "2026-09-26T10:00:00+00:00"),
        ("2026-09-26 10:00 CST", "-06:00", "2026-09-26T16:00:00+00:00"),
    ],
)
def test_upstream_calendar_and_explicit_zone_cases(value, offset, expected):
    assert parse_loose_date(value, offset) == datetime.fromisoformat(expected)


@pytest.mark.parametrize("kind", ["rss", "web_list", "json_list"])
def test_source_offset_configuration_rejects_invalid_values(kind):
    from pydantic import ValidationError

    options = (
        {"feed_url": "https://example.com/feed"}
        if kind == "rss"
        else {"url": "https://example.com/list", "item_selector": "article"}
        if kind == "web_list"
        else {
            "url": "https://example.com/list",
            "title_paths": ["title"],
            "url_template": "https://example.com/{id}",
        }
    )
    assert config(kind, **options).published_at_utc_offset == "+08:00"
    for invalid in ("Asia/Shanghai", "08:00", "+25:00", "+08:60"):
        with pytest.raises(ValidationError):
            config(kind, **options, published_at_utc_offset=invalid)


def test_first_import_detail_date_recheck_does_not_repeat_url_rewrite():
    c = config(
        "web_list",
        url="https://example.com/list",
        item_selector="article",
        item_url_prefix_rewrite={
            "from_prefix": "https://example.com/",
            "to_prefix": "https://example.com/rewritten/",
        },
    )
    http, _ = admitted_http(
        lambda request: httpx.Response(
            200,
            text='<article><a href="/post">Unknown date</a></article>',
        )
    )
    registry = EditorialSourceRegistry(http=http, clock=lambda: NOW, source_added_at=NOW)
    try:
        page = registry.collect(profile(c), EditorialCursor(), {})
        assert page.status == "complete" and len(page.materials) == 1
        assert page.materials[0].url == "https://example.com/rewritten/post"
    finally:
        registry.close()
