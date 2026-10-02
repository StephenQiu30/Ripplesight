from content.editorial_rendered import prepare_editorial_rendered
from sources.editorial_schemas import EditorialMaterial


def test_rendered_preserves_format_and_hashes_html_only_changes() -> None:
    one = EditorialMaterial(
        url="https://example.com/a",
        identity_key="a",
        title="A",
        body_status="ok",
        body_text="hello",
        body_html='<p>hello<img src="/one.png" onerror="bad()"></p>',
        content_format="html",
    )
    two = one.model_copy(update={"body_html": '<strong>hello<img src="/one.png"></strong>'})
    prepared = prepare_editorial_rendered(one)
    assert prepared.body_format == "html"
    assert "<p>" in prepared.body
    assert "onerror" not in prepared.body
    assert prepared.media[0].url == "https://example.com/one.png"
    assert prepared.sha256 != prepare_editorial_rendered(two).sha256
    assert len(bytes.fromhex(prepared.sha256)) == 32


def test_rendered_markdown_and_media_are_part_of_frozen_identity() -> None:
    one = EditorialMaterial(
        url="https://example.com/a",
        identity_key="a",
        title="A",
        body_status="ok",
        body_text="hello",
        body_markdown="**hello**",
        content_format="markdown",
        media=("https://example.com/one.png",),
    )
    prepared = prepare_editorial_rendered(one)
    assert prepared.body == "**hello**"
    assert prepared.body_format == "markdown"
    changed = one.model_copy(update={"media": ("https://example.com/two.png",)})
    assert prepared.sha256 != prepare_editorial_rendered(changed).sha256


def test_safe_original_layout_survives_collector_and_storage_sanitization() -> None:
    from sources.adapters.editorial_parsing import sanitize_html

    body = (
        '<h2 id="章节-1" onclick="bad()">Title</h2>'
        '<a href="#章节-1">jump</a><pre><code class="language-python other">code</code></pre>'
        '<table><tr><td colspan="2" rowspan="3" style="position:fixed">cell</td></tr></table>'
        '<video controls poster="/poster.png" onload="bad()"><source src="/film.mp4"></video>'
        '<picture><source srcset="/small.png 1x, /large.png 2x, javascript:bad 3x">'
        '<img src="/base.png" alt="Image"></picture><script>bad()</script>'
    )
    safe, text = sanitize_html(body, "https://example.com/a")
    prepared = prepare_editorial_rendered(
        EditorialMaterial(
            url="https://example.com/a",
            identity_key="a",
            title="A",
            body_status="ok",
            body_text=text,
            body_html=safe,
            content_format="html",
        )
    )
    assert 'id="章节-1"' in prepared.body
    assert 'class="language-python"' in prepared.body
    assert 'colspan="2"' in prepared.body and 'rowspan="3"' in prepared.body
    assert "controls" in prepared.body and "poster=" in prepared.body
    assert "srcset=" in prepared.body
    assert all(
        term not in prepared.body
        for term in ("onclick", "onload", "style=", "javascript", "<script")
    )
    assert {m.url for m in prepared.media} == {
        "https://example.com/poster.png",
        "https://example.com/film.mp4",
        "https://example.com/small.png",
        "https://example.com/large.png",
        "https://example.com/base.png",
    }
