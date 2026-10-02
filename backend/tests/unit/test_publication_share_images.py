from io import BytesIO

import pytest
from PIL import Image

from publication.share_images import ShareCard, render_share_png


def test_share_png_uses_local_chinese_glyphs_and_is_deterministic():
    card = ShareCard(
        kicker="模型发布",
        title="真实中文模型更新",
        summary="固定许可摘要",
        meta="许可来源 · 2026-10-02",
        canonical_url="https://hotkey.example/items/fixed",
        score=90,
    )
    result = render_share_png(card)
    assert result == render_share_png(card)
    with Image.open(BytesIO(result)) as image:
        assert image.format == "PNG" and image.size == (1200, 630)
        assert len(image.getcolors(maxcolors=1_000_000)) > 10
    assert result != render_share_png(
        ShareCard(kicker="模型发布", title="另一份当前模型", canonical_url=card.canonical_url)
    )
    poster = render_share_png(card, poster=True)
    with Image.open(BytesIO(poster)) as image:
        assert image.size == (1080, 1440)
        # Quiet border is white; QR central region has both black and white exact modules.
        assert image.getpixel((804, 1204)) == (255, 255, 255)
        assert set(image.crop((804, 1204, 1004, 1404)).get_flattened_data()) == {
            (0, 0, 0),
            (255, 255, 255),
        }


def test_share_input_cannot_encode_credentials_or_arbitrary_navigation():
    with pytest.raises(ValueError):
        render_share_png(
            ShareCard(
                kicker="新闻",
                title="材料",
                canonical_url="https://user:secret@hotkey.example/items/fixed",
            ),
            poster=True,
        )
    with pytest.raises(ValueError):
        render_share_png(
            ShareCard(kicker="新闻", title="材料", canonical_url="javascript:alert(1)"), poster=True
        )
