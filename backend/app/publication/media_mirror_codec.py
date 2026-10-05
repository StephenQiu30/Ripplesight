"""AIHOT fixed image renditions, adapted under MIT; header gates precede native decoding."""

from __future__ import annotations

import io
import re
import struct
import warnings
from dataclasses import dataclass
from xml.etree import ElementTree

from PIL import Image, ImageOps

IMAGE_WIDTHS = {
    "avatar": 96,
    "card": 336,
    "thumb": 720,
    "full": 1600,
    "og": 1200,
    "avatar-48": 48,
    "avatar-96": 96,
    "image-336": 336,
    "image-720": 720,
    "image-1200": 1200,
    "image-1600": 1600,
}
MAX_IMAGE_PIXELS = 50_000_000
MAX_ANIMATION_PIXELS = 200_000_000
_SVG_TAGS = {
    "svg",
    "g",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
    "title",
    "desc",
    "use",
}


@dataclass(frozen=True)
class EncodedRendition:
    mode: str
    body: bytes
    mime_type: str
    width: int
    height: int
    frame_count: int = 1


def _dimensions(width: int, height: int) -> tuple[int, int]:
    if min(width, height) < 1 or max(width, height) > 50000 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("image dimensions exceed the decode limit")
    return width, height


def _svg(body: bytes) -> tuple[bytes, int, int]:
    if len(body) > 128 * 1024 or b"\0" in body:
        raise ValueError("unsupported SVG declaration or size")
    try:
        source = body.decode("utf-8-sig")
        source = re.sub(r"^\s*<\?xml\s+[^?]{0,256}\?>", "", source, count=1)
        if "<?" in source or "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
            raise ValueError("active SVG declaration")
        root = ElementTree.fromstring(source)
    except (ElementTree.ParseError, UnicodeError) as error:
        raise ValueError("invalid SVG") from error
    if root.tag.split("}")[-1] != "svg":
        raise ValueError("not an SVG")
    nodes = list(root.iter())
    if len(nodes) > 2000:
        raise ValueError("SVG node limit")
    for node in nodes:
        if node.tag.split("}")[-1] not in _SVG_TAGS:
            raise ValueError("active or unsupported SVG element")
        for name, value in node.attrib.items():
            key = name.split("}")[-1].lower()
            if (
                key.startswith("on")
                or key in {"style", "src"}
                or (key == "href" and not re.fullmatch(r"#[A-Za-z0-9_-]+", value))
                or re.search(r"url\(\s*(?!#[A-Za-z0-9_-]+\))", value, re.I)
            ):
                raise ValueError("active or external SVG attribute")
    viewbox = root.get("viewBox", "").replace(",", " ").split()

    def numeric(value: str | None, fallback: str) -> int:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)(?:px)?", value or fallback)
        if match is None:
            raise ValueError("SVG needs bounded dimensions")
        return max(1, int(float(match[1])))

    width = numeric(root.get("width"), viewbox[2] if len(viewbox) == 4 else "300")
    height = numeric(root.get("height"), viewbox[3] if len(viewbox) == 4 else "150")
    _dimensions(width, height)
    return ElementTree.tostring(root, encoding="utf-8"), width, height


def validate_media_header(body: bytes, *, kind: str) -> tuple[str, int | None, int | None]:
    if not body:
        raise ValueError("empty media")
    if kind == "video":
        if (
            len(body) >= 24
            and body[4:8] == b"ftyp"
            and body[8:12]
            in {b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"qt  ", b"M4V ", b"M4A "}
        ):
            if body[8:12] == b"M4A ":
                raise ValueError("audio is not a video")
            return "video/mp4", None, None
        if body.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in body[:4096]:
            return "video/webm", None, None
        if body.startswith(b"OggS") and b"theora" in body[:4096]:
            return "video/ogg", None, None
        raise ValueError("unsupported video magic")
    mime: str
    width: int
    height: int
    if body.startswith(b"\x89PNG\r\n\x1a\n") and len(body) >= 24 and body[12:16] == b"IHDR":
        width, height = struct.unpack(">II", body[16:24])
        mime = "image/png"
    elif body[:6] in {b"GIF87a", b"GIF89a"} and len(body) >= 10:
        width, height = struct.unpack("<HH", body[6:10])
        mime = "image/gif"
    elif body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        chunk = body[12:16]
        if chunk == b"VP8X" and len(body) >= 30:
            width = 1 + int.from_bytes(body[24:27], "little")
            height = 1 + int.from_bytes(body[27:30], "little")
        elif chunk == b"VP8L" and len(body) >= 25 and body[20] == 47:
            bits = int.from_bytes(body[21:25], "little")
            width = 1 + (bits & 0x3FFF)
            height = 1 + ((bits >> 14) & 0x3FFF)
        elif chunk == b"VP8 " and len(body) >= 30 and body[23:26] == b"\x9d\x01\x2a":
            width, height = (n & 0x3FFF for n in struct.unpack("<HH", body[26:30]))
        else:
            raise ValueError("unsupported WebP header")
        mime = "image/webp"
    elif body.startswith(b"\xff\xd8"):
        position = 2
        width = height = 0
        while position + 4 <= len(body):
            if body[position] != 255:
                raise ValueError("invalid JPEG marker")
            while position < len(body) and body[position] == 255:
                position += 1
            marker = body[position]
            position += 1
            if marker in {0xD8, 0xD9, 0xDA}:
                break
            size = int.from_bytes(body[position : position + 2], "big")
            if size < 2 or position + size > len(body):
                raise ValueError("invalid JPEG segment")
            if (
                marker
                in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
                and size >= 7
            ):
                height, width = struct.unpack(">HH", body[position + 3 : position + 7])
                break
            position += size
        mime = "image/jpeg"
    elif body.startswith(b"\x00\x00\x01\x00") and len(body) >= 22:
        count = int.from_bytes(body[4:6], "little")
        if not 1 <= count <= 256 or len(body) < 6 + 16 * count:
            raise ValueError("invalid ICO table")
        dimensions = []
        for index in range(count):
            offset = 6 + index * 16
            length, start = struct.unpack("<II", body[offset + 8 : offset + 16])
            if start < 6 + 16 * count or start + length > len(body):
                raise ValueError("invalid ICO payload")
            dimensions.append((body[offset] or 256, body[offset + 1] or 256))
        width, height = max(dimensions, key=lambda item: item[0] * item[1])
        mime = "image/x-icon"
    elif body.lstrip().startswith((b"<svg", b"<?xml", b"<!--", b"\xef\xbb\xbf<")):
        _, width, height = _svg(body)
        mime = "image/svg+xml"
    else:
        raise ValueError("unsupported image magic")
    _dimensions(width, height)
    return mime, width, height


def encode_avatar_renditions(body: bytes) -> tuple[EncodedRendition, ...]:
    """Source icons have a deliberate still-first-frame contract and only two square sizes."""
    mime, _, _ = validate_media_header(body, kind="image")
    targets = {"avatar-48": 48, "avatar-96": 96}
    if mime == "image/svg+xml":
        safe, width, height = _svg(body)
        result = []
        for mode, size in targets.items():
            root = ElementTree.fromstring(safe)
            root.set("viewBox", root.get("viewBox") or f"0 0 {width} {height}")
            root.set("width", str(size))
            root.set("height", str(size))
            root.set("preserveAspectRatio", "xMidYMid slice")
            result.append(EncodedRendition(mode, ElementTree.tostring(root), mime, size, size))
        return tuple(result)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(body)) as image:
                image.seek(0)
                image.load()
                oriented = ImageOps.exif_transpose(image).convert("RGBA")
                results = []
                for mode, size in targets.items():
                    resized = ImageOps.fit(oriented, (size, size), Image.Resampling.LANCZOS)
                    output = io.BytesIO()
                    resized.save(output, format="WEBP", quality=88, method=4)
                    results.append(
                        EncodedRendition(mode, output.getvalue(), "image/webp", size, size)
                    )
                return tuple(results)
    except (
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("invalid or oversized source icon") from error


def encode_image_renditions(body: bytes) -> tuple[EncodedRendition, ...]:
    mime, width, height = validate_media_header(body, kind="image")
    assert width is not None and height is not None
    if mime == "image/svg+xml":
        safe, width, height = _svg(body)
        result = []
        svg_variants: dict[tuple[bool, int, int], bytes] = {}
        for mode, target in IMAGE_WIDTHS.items():
            actual = target if mode.startswith("avatar") else min(width, target)
            out_height = (
                actual if mode.startswith("avatar") else max(1, round(height * actual / width))
            )
            svg_key = (mode.startswith("avatar"), actual, out_height)
            if svg_key not in svg_variants:
                root = ElementTree.fromstring(safe)
                root.set("viewBox", root.get("viewBox") or f"0 0 {width} {height}")
                root.set("width", str(actual))
                root.set("height", str(out_height))
                root.set(
                    "preserveAspectRatio",
                    "xMidYMid slice" if mode.startswith("avatar") else "xMidYMid meet",
                )
                svg_variants[svg_key] = ElementTree.tostring(root, encoding="utf-8")
            result.append(EncodedRendition(mode, svg_variants[svg_key], mime, actual, out_height))
        return tuple(result)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(body))
            frame_count = getattr(image, "n_frames", 1)
            if frame_count > 1000 or width * height * frame_count > MAX_ANIMATION_PIXELS:
                raise ValueError("animation decode limit")
            if frame_count > 1 or mime == "image/gif":
                frames, delays = [], []
                for index in range(frame_count):
                    image.seek(index)
                    image.load()
                    frames.append(image.convert("RGBA").copy())
                    delays.append(image.info.get("duration", 100))
                loop = image.info.get("loop", 0)
                image.close()
                variants: dict[int, tuple[bytes, str, int, int]] = {}
                results = []
                for mode, target in IMAGE_WIDTHS.items():
                    actual = min(width, target)
                    out_height = max(1, round(height * actual / width))
                    if actual not in variants:
                        resized_frames = [
                            frame.resize((actual, out_height), Image.Resampling.LANCZOS)
                            if actual != width
                            else frame
                            for frame in frames
                        ]
                        encoded = io.BytesIO()
                        resized_frames[0].save(
                            encoded,
                            format="WEBP",
                            save_all=True,
                            append_images=resized_frames[1:],
                            duration=delays,
                            loop=loop,
                            quality=80,
                            method=4,
                        )
                        alternative = encoded.getvalue()
                        variants[actual] = (
                            (alternative, "image/webp", actual, out_height)
                            if len(alternative) <= len(body) * 0.85
                            else (body, mime, width, height)
                        )
                    animation_body, output_mime, output_width, output_height = variants[actual]
                    results.append(
                        EncodedRendition(
                            mode,
                            animation_body,
                            output_mime,
                            output_width,
                            output_height,
                            frame_count,
                        )
                    )
                return tuple(results)
            image.load()
            oriented = ImageOps.exif_transpose(image)
            results = []
            still_variants: dict[tuple[bool, tuple[int, int]], bytes] = {}
            for mode, target in IMAGE_WIDTHS.items():
                resized = (
                    ImageOps.fit(oriented, (target, target), Image.Resampling.LANCZOS)
                    if mode.startswith("avatar")
                    else oriented.copy()
                )
                if not mode.startswith("avatar"):
                    resized.thumbnail((target, 50000), Image.Resampling.LANCZOS)
                webp = mime in {"image/png", "image/webp", "image/x-icon"}
                key = (mode.startswith("avatar"), resized.size)
                if key not in still_variants:
                    output = io.BytesIO()
                    resized = resized.convert("RGBA" if webp else "RGB")
                    resized.save(
                        output,
                        format="WEBP" if webp else "JPEG",
                        quality=88 if webp and mime != "image/webp" else 82,
                        method=4 if webp else 0,
                    )
                    still_variants[key] = output.getvalue()
                results.append(
                    EncodedRendition(
                        mode,
                        still_variants[key],
                        "image/webp" if webp else "image/jpeg",
                        resized.width,
                        resized.height,
                    )
                )
            return tuple(results)
    except (
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("invalid or oversized image") from error
