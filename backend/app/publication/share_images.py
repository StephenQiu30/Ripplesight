"""AIHOT share intent under MIT; offline Pillow rendering with separately licensed OFL fonts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import qrcode
from PIL import Image, ImageDraw, ImageFont

from publication.exports import safe_link

_FONTS = Path(__file__).with_name("assets") / "og-fonts"


@dataclass(frozen=True, slots=True)
class ShareCard:
    kicker: str
    title: str
    canonical_url: str
    summary: str = ""
    meta: str = ""
    score: float | None = None


@lru_cache(maxsize=24)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS / f"noto-sans-sc-{700 if bold else 400}.ttf"), size)


def _clamp(value: str, maximum: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= maximum else value[: maximum - 1] + "…"


def _lines(value: str, *, font: ImageFont.FreeTypeFont, width: int, maximum: int) -> list[str]:
    lines, current = [], ""
    remaining = _clamp(value, 2000)
    for index, character in enumerate(remaining):
        if current and font.getlength(current + character) > width:
            lines.append(current)
            current = character
            if len(lines) == maximum:
                lines[-1] = lines[-1][:-1] + "…"
                return lines
        else:
            current += character
        if index == len(remaining) - 1:
            lines.append(current)
    return lines[:maximum]


def _text(
    draw: ImageDraw.ImageDraw,
    value: str,
    *,
    x: int,
    y: int,
    width: int,
    size: int,
    maximum: int,
    color: str,
    bold: bool = False,
) -> int:
    font = _font(size, bold)
    step = int(size * 1.45)
    lines = _lines(value, font=font, width=width, maximum=maximum)
    for index, line in enumerate(lines):
        draw.text((x, y + index * step), line, font=font, fill=color, anchor="lt")
    return y + len(lines) * step


def _qr(url: str) -> Image.Image:
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    code.add_data(url)
    code.make(fit=True)
    matrix = code.get_matrix()
    result = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(result)
    side = len(matrix)
    box = 200 // side
    if box < 2:
        raise ValueError("canonical URL exceeds readable poster QR capacity")
    padding = (200 - side * box) // 2
    for y, row in enumerate(matrix):
        for x, filled in enumerate(row):
            if filled:
                draw.rectangle(
                    (
                        padding + x * box,
                        padding + y * box,
                        padding + (x + 1) * box - 1,
                        padding + (y + 1) * box - 1,
                    ),
                    fill="black",
                )
    return result


def render_share_png(card: ShareCard, *, poster: bool = False) -> bytes:
    if not safe_link(card.canonical_url) or len(card.canonical_url) > 500:
        raise ValueError("share image requires a bounded canonical HTTP(S) URL")
    size = (1080, 1440) if poster else (1200, 630)
    image = Image.new("RGB", size, "#f7f7f5" if poster else "#101214")
    draw = ImageDraw.Draw(image)
    ink, muted, accent = (
        ("#101214", "#53616b", "#176b75") if poster else ("#ffffff", "#b7bec4", "#49cdd5")
    )
    margin = 84 if poster else 72
    _text(
        draw,
        "Ripplesight",
        x=margin,
        y=70 if poster else 46,
        width=400,
        size=42 if poster else 34,
        maximum=1,
        color=ink,
        bold=True,
    )
    _text(
        draw,
        urlsplit(card.canonical_url).netloc,
        x=600 if poster else 750,
        y=84 if poster else 56,
        width=390,
        size=20,
        maximum=1,
        color=muted,
    )
    _text(
        draw,
        _clamp(card.kicker, 40),
        x=margin,
        y=222 if poster else 140,
        width=900,
        size=30 if poster else 26,
        maximum=1,
        color=accent,
        bold=True,
    )
    title = _clamp(card.title, 72 if poster else 64)
    title_size = (
        (58 if len(title) > 48 else 66 if len(title) > 30 else 76)
        if poster
        else (50 if len(title) > 40 else 58 if len(title) > 24 else 66)
    )
    end = _text(
        draw,
        title,
        x=margin,
        y=290 if poster else 196,
        width=size[0] - margin * 2,
        size=title_size,
        maximum=4 if poster else 3,
        color=ink,
        bold=True,
    )
    summary_y = end + (58 if poster else 20)
    summary_size = 34 if poster else 27
    summary_max = max(
        0,
        min(
            10 if poster else 2, ((1120 if poster else 515) - summary_y) // int(summary_size * 1.45)
        ),
    )
    _text(
        draw,
        _clamp(card.summary, 360 if poster else 120),
        x=margin,
        y=summary_y,
        width=size[0] - margin * 2,
        size=summary_size,
        maximum=summary_max,
        color=muted,
    )
    if poster:
        draw.line((margin, 1145, size[0] - margin, 1145), fill="#d7dce0", width=2)
        _text(draw, card.meta, x=margin, y=1200, width=680, size=24, maximum=2, color=muted)
        _text(
            draw, card.canonical_url, x=margin, y=1300, width=640, size=18, maximum=3, color=muted
        )
        image.paste(_qr(card.canonical_url), (804, 1204))
    else:
        draw.line((margin, 515, size[0] - margin, 515), fill="#3d4145", width=2)
        _text(draw, card.meta, x=margin, y=550, width=850, size=22, maximum=1, color=muted)
    if card.score is not None:
        value = f"精选评分 {card.score:.0f}"
        _text(
            draw,
            value,
            x=margin if poster else 950,
            y=1068 if poster else 550,
            width=300 if poster else 180,
            size=26 if poster else 20,
            maximum=1,
            color=accent,
            bold=True,
        )
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
