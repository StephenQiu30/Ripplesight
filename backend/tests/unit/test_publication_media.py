from xml.etree import ElementTree

from publication.media import body_presentation
from publication.posters import item_poster
from publication.schemas import PublicMediaView
from tests.unit.test_publication_exports import detail


def test_explicit_markdown_keeps_code_tables_outline_and_links_without_network_images() -> None:
    html, outline, media = body_presentation(
        "## 结构\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n`print(1)`\n\n![图片](https://example.com/image.png)",
        body_format="markdown",
    )
    assert "<table>" in html and "<code>print(1)</code>" in html
    assert len(outline) == 1 and f'id="{outline[0].id}"' in html
    assert len(media) == 1 and media[0].original_url == "https://example.com/image.png"
    assert media[0].reading_url is None and media[0].state == "original_link"
    assert "<img" not in html and "https://example.com/image.png" in html


def test_html_strips_script_and_unsafe_attributes_and_complex_input_falls_back_to_text() -> None:
    rendered, _, _ = body_presentation(
        "<h2>标题</h2><script>alert(1)</script>"
        '<a href="javascript:bad" onclick="bad">正文</a>'
        '<img src="https://example.com/a" onerror="bad">',
        body_format="html",
    )
    assert "script" not in rendered and "javascript" not in rendered and "onclick" not in rendered
    assert "<img" not in rendered and '<a href="https://example.com/a">' in rendered
    huge = "<div>" * 100 + "完整保留文本" + "</div>" * 100
    fallback, outline, media = body_presentation(huge, body_format="html")
    assert "完整保留文本" in fallback and "&lt;div&gt;" in fallback
    assert not outline and not media


def test_video_nested_source_survives_as_safe_original_link() -> None:
    html, _, media = body_presentation(
        '<video><source src="https://example.com/movie.mp4"></video>', body_format="html"
    )
    assert len(media) == 1 and media[0].kind == "video"
    assert media[0].original_url == "https://example.com/movie.mp4"
    assert '<a href="https://example.com/movie.mp4">' in html
    assert "<video" not in html and "<source" not in html


def test_fixed_metadata_media_is_visible_and_only_verified_owned_images_are_embedded() -> None:
    metadata = PublicMediaView(
        key="fixed-photo",
        kind="image",
        original_url="https://example.com/photo",
        alt="官方附件",
        reading_url=None,
        state="original_link",
    )
    rendered, _, media = body_presentation("只含文本", media=(metadata,))
    assert '<a href="https://example.com/photo">官方附件</a>' in rendered
    assert media == [metadata] and "<img" not in rendered
    saved = metadata.model_copy(
        update={
            "state": "available",
            "reading_url": "/api/publication/media/fixed/full/site",
            "width": 900,
            "height": 300,
        }
    )
    rendered, _, media = body_presentation(
        "只含文本", media=(metadata,), mirrored={saved.key: saved}
    )
    assert 'src="/api/publication/media/fixed/full/site"' in rendered
    assert "https://example.com/photo" not in rendered and media == [saved]
    unknown = metadata.model_copy(update={"kind": "unknown", "key": "unknown"})
    rendered, _, media = body_presentation("只含文本", media=(unknown,))
    assert media == [unknown] and "<img" not in rendered and "<video" not in rendered


def test_svg_poster_is_local_escaped_and_summary_mode_disables_output() -> None:
    item = detail()
    poster = item_poster(item, origin="https://hotkey.example")
    root = ElementTree.fromstring(poster)
    assert root.attrib["width"] == "1080" and root.attrib["height"] == "1440"
    assert "<script>" not in poster and "<image" not in poster and "<foreignObject" not in poster
    assert "来源" in poster and "hotkey.example/items/fixed" in poster
    assert (
        item_poster(
            item.model_copy(update={"markdown_available": False}), origin="https://hotkey.example"
        )
        is None
    )
