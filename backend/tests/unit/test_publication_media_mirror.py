import io
import struct

import pytest
from PIL import Image

from publication.media_mirror_codec import (
    IMAGE_WIDTHS,
    encode_image_renditions,
    validate_media_header,
)


def image_bytes(format: str, size: tuple[int, int] = (900, 300)) -> bytes:
    output = io.BytesIO()
    Image.new("RGBA" if format == "PNG" else "RGB", size, "red").save(output, format=format)
    return output.getvalue()


def test_real_raster_renditions_do_not_enlarge_and_avatar_crops() -> None:
    encoded = encode_image_renditions(image_bytes("PNG"))
    assert {item.mode for item in encoded} == set(IMAGE_WIDTHS)
    for item in encoded:
        decoded = Image.open(io.BytesIO(item.body))
        assert decoded.format == "WEBP"
        assert item.width == decoded.width and item.height == decoded.height
        if item.mode.startswith("avatar"):
            assert decoded.size == (IMAGE_WIDTHS[item.mode], IMAGE_WIDTHS[item.mode])
        else:
            assert decoded.width == min(900, IMAGE_WIDTHS[item.mode])


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_static_aliases_encode_once_per_actual_size_and_crop_without_cross_call_cache(
    monkeypatch, format
):
    body = image_bytes(format)
    calls = []
    save = Image.Image.save

    def counted(image, *args, **kwargs):
        calls.append((image.size, kwargs.get("format")))
        return save(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", counted)
    result = {item.mode: item for item in encode_image_renditions(body)}
    assert len(calls) == 5  # Two square crops and three un-enlarged landscape sizes.
    assert set(result) == set(IMAGE_WIDTHS)
    for aliases in (("avatar", "avatar-96"), ("card", "image-336"), ("thumb", "image-720")):
        assert result[aliases[0]].body is result[aliases[1]].body
    assert result["full"].body is result["og"].body is result["image-1200"].body
    assert result["full"].body is result["image-1600"].body
    for item in result.values():
        with Image.open(io.BytesIO(item.body)) as decoded:
            assert decoded.size == (item.width, item.height)
            assert decoded.format == ("JPEG" if format == "JPEG" else "WEBP")
    encode_image_renditions(body)
    assert len(calls) == 10


def test_static_reuse_uses_exif_corrected_dimensions_and_separates_square_crop(monkeypatch):
    output = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (900, 300), "red").save(output, format="JPEG", exif=exif)
    calls = []
    save = Image.Image.save

    def counted(image, *args, **kwargs):
        calls.append(image.size)
        return save(image, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", counted)
    result = {item.mode: item for item in encode_image_renditions(output.getvalue())}
    assert calls == [(96, 96), (300, 900), (48, 48)]
    assert (result["card"].width, result["card"].height) == (300, 900)
    assert result["card"].body is result["full"].body
    calls.clear()
    square = io.BytesIO()
    save(Image.new("RGB", (96, 96), "blue"), square, format="PNG")
    encode_image_renditions(square.getvalue())
    assert calls == [(96, 96), (96, 96), (48, 48)]


def test_svg_size_and_active_resource_bounds_stay_closed():
    for body in (
        b'<svg width="200" height="100"><desc>' + b"a" * (128 * 1024) + b"</desc></svg>",
        b'<svg width="200" height="100">' + b"<g/>" * 2000 + b"</svg>",
        b'<svg width="200" height="100"><use href="https://example.com/a"/></svg>',
    ):
        with pytest.raises(ValueError):
            encode_image_renditions(body)
    result = encode_image_renditions(b'<svg width="200" height="100"><rect/></svg>')
    assert all(
        item.width == 200 and item.height == 100 for item in result if "avatar" not in item.mode
    )


def test_safe_svg_aliases_serialize_once_per_size_and_crop(monkeypatch):
    from xml.etree import ElementTree

    calls = []
    serialize = ElementTree.tostring

    def counted(root, *args, **kwargs):
        calls.append((root.get("width"), root.get("height"), root.get("preserveAspectRatio")))
        return serialize(root, *args, **kwargs)

    monkeypatch.setattr(ElementTree, "tostring", counted)
    result = {
        item.mode: item
        for item in encode_image_renditions(b'<svg width="200" height="100"><rect/></svg>')
    }
    assert len(calls) == 5  # Two bounded normalization passes, then only three output geometries.
    assert result["avatar"].body is result["avatar-96"].body
    assert all(
        result[mode].body is result["full"].body for mode in IMAGE_WIDTHS if "avatar" not in mode
    )
    assert b"xMidYMid slice" in result["avatar"].body
    assert b"xMidYMid meet" in result["full"].body


def test_icon_avatar_codec_only_decodes_first_frame_and_two_square_sizes():
    from publication.media_mirror_codec import encode_avatar_renditions

    source = io.BytesIO()
    frames = [Image.new("RGBA", (120, 40), colour) for colour in ("red", "green")]
    frames[0].save(
        source, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0
    )
    result = encode_avatar_renditions(source.getvalue())
    assert {item.mode for item in result} == {"avatar-48", "avatar-96"}
    for item in result:
        with Image.open(io.BytesIO(item.body)) as image:
            assert image.size == (IMAGE_WIDTHS[item.mode], IMAGE_WIDTHS[item.mode])
            assert getattr(image, "n_frames", 1) == item.frame_count == 1
            red, green, blue, *_ = image.getpixel((image.width // 2, image.height // 2))
            assert red > 200 and green < 30 and blue < 30
    with pytest.raises(ValueError):
        encode_avatar_renditions(b"<html>not an image</html>")


def test_animation_preserves_frames_delay_loop_and_never_becomes_still() -> None:
    source = io.BytesIO()
    frames = [Image.new("RGBA", (40, 30), colour) for colour in ["red", "green", "blue"]]
    frames[0].save(
        source,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[100, 200, 300],
        loop=2,
    )
    result = encode_image_renditions(source.getvalue())
    for rendition in result:
        image = Image.open(io.BytesIO(rendition.body))
        assert image.n_frames == 3 and image.info["loop"] == 2
        delays = []
        for index in range(3):
            image.seek(index)
            image.load()
            delays.append(image.info["duration"])
        assert delays == [100, 200, 300]


def test_beneficial_animated_conversion_uses_each_rendition_width_and_keeps_timing():
    source = io.BytesIO()
    frames = [Image.effect_noise((900, 300), 64).convert("RGBA") for _ in range(3)]
    frames[0].save(
        source,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[100, 200, 300],
        loop=2,
    )
    body = source.getvalue()
    encoded = {value.mode: value for value in encode_image_renditions(body)}
    for mode in ("card", "image-720"):
        rendition = encoded[mode]
        assert rendition.mime_type == "image/webp"
        assert len(rendition.body) < len(body) * 0.85
        with Image.open(io.BytesIO(rendition.body)) as image:
            assert image.size == (
                min(900, IMAGE_WIDTHS[mode]),
                round(300 * min(900, IMAGE_WIDTHS[mode]) / 900),
            )
            assert rendition.width == image.width and rendition.height == image.height
            assert image.n_frames == rendition.frame_count == 3 and image.info["loop"] == 2
            delays = []
            for index in range(3):
                image.seek(index)
                image.load()
                delays.append(image.info["duration"])
            assert delays == [100, 200, 300]
    assert encoded["full"].body == body and encoded["full"].mime_type == "image/gif"
    assert (encoded["full"].width, encoded["full"].height) == (900, 300)


def test_magic_and_dimensions_are_checked_before_native_decoder() -> None:
    with pytest.raises(ValueError):
        validate_media_header(b"<html>error</html>", kind="image")
    huge_png = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", 100000, 100000)
        + b"\x08\x06\x00\x00\x00"
    )
    with pytest.raises(ValueError):
        validate_media_header(huge_png, kind="image")
    with pytest.raises(ValueError):
        validate_media_header(
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', kind="image"
        )
    assert (
        validate_media_header(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 12, kind="video")[0]
        == "video/mp4"
    )


def test_inert_svg_xml_declaration_and_comments_are_supported_but_entities_are_rejected() -> None:
    body = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n<!-- owned icon -->'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
        b'<rect width="200" height="100" fill="red"/></svg>'
    )
    assert validate_media_header(body, kind="image") == ("image/svg+xml", 200, 100)
    renditions = encode_image_renditions(body)
    assert len(renditions) == 11
    assert b"<?xml" not in renditions[0].body and b"<!--" not in renditions[0].body
    for declaration in [
        b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>',
        b'<?xml-stylesheet href="https://private.example/style.css"?>',
    ]:
        with pytest.raises(ValueError):
            validate_media_header(declaration + body, kind="image")


def test_dns_pinning_rejects_private_and_budgets_each_redirect_and_byte_limit() -> None:
    import httpx

    from publication.media_mirror_fetch import MediaMirrorClient, public_target

    for value in ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"]:
        with pytest.raises(ValueError):
            public_target(
                "https://images.example/a.png", resolver=lambda host, address=value: (address,)
            )
    calls, outcomes = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "images.example"
        assert request.extensions["sni_hostname"] == "images.example"
        return (
            httpx.Response(302, headers={"location": "/real.png"})
            if request.url.path == "/a.png"
            else httpx.Response(200, content=image_bytes("PNG"))
        )

    client = MediaMirrorClient(
        enabled=True,
        before_request=lambda index: True,
        after_request=lambda index, result: outcomes.append((index, result)),
        resolver=lambda host: ("8.8.8.8",),
        transport=httpx.MockTransport(handler),
    )
    assert client.fetch("https://images.example/a.png", kind="image").mime_type == "image/png"
    assert len(calls) == 2 and outcomes == [(1, "succeeded"), (2, "succeeded")]
    client.close()


def test_icon_document_fetch_uses_same_pinned_metered_transport_and_explicit_html_cap():
    import httpx

    from publication.media_mirror_fetch import MediaMirrorClient

    calls, outcomes = [], []

    def handler(request):
        calls.append(request)
        assert request.url.host == "8.8.8.8" and request.headers["host"] == "icons.example"
        assert request.extensions["sni_hostname"] == "icons.example"
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/homepage"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html>" + b"a" * 2_000_001 + b"</html>",
        )

    client = MediaMirrorClient(
        enabled=True,
        before_request=lambda i: True,
        after_request=lambda i, state: outcomes.append((i, state)),
        resolver=lambda _: ("8.8.8.8",),
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.fetch_document("https://icons.example/", max_bytes=4_000_000)
        assert len(result.body) > 2_000_000 and result.final_url.endswith("/homepage")
        assert outcomes == [(1, "succeeded"), (2, "succeeded")]
        with pytest.raises(ValueError, match="byte limit"):
            client.fetch_document("https://icons.example/homepage", max_bytes=100)
        assert outcomes[-1] == (1, "failed")
        with pytest.raises(ValueError, match="at most"):
            client.fetch_document("https://icons.example/", max_bytes=10_000_001)
    finally:
        client.close()
    client = MediaMirrorClient(
        enabled=True,
        before_request=lambda index: True,
        after_request=lambda index, result: outcomes.append((index, result)),
        resolver=lambda host: ("8.8.8.8",),
        image_max_bytes=4,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"12345")),
    )
    with pytest.raises(ValueError):
        client.fetch("https://images.example/a.png", kind="image")
    assert outcomes[-1] == (1, "failed")
    client.close()
    zero = []
    client = MediaMirrorClient(
        before_request=lambda index: True,
        after_request=lambda index, result: None,
        transport=httpx.MockTransport(lambda request: zero.append(request) or httpx.Response(200)),
    )
    with pytest.raises(PermissionError):
        client.fetch("https://images.example/a.png", kind="image")
    assert not zero
    client.close()
