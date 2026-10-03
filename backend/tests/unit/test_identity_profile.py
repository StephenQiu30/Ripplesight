import base64
from io import BytesIO

import pytest
from PIL import Image

from core.errors import ApplicationError
from identity.profile_schemas import IdentityAvatarInput, IdentityProfileInput
from identity.profile_services import normalize_avatar


def image_input(
    mime: str = "image/png", *, size: tuple[int, int] = (80, 40)
) -> IdentityAvatarInput:
    output = BytesIO()
    Image.new("RGB", size, (50, 60, 70)).save(output, format="PNG")
    return IdentityAvatarInput(mime=mime, data_base64=base64.b64encode(output.getvalue()).decode())


def test_avatar_is_square_bounded_and_contains_no_original_metadata() -> None:
    normalized = normalize_avatar(image_input())
    with Image.open(BytesIO(normalized)) as image:
        assert image.size == (256, 256)
        assert image.format == "PNG"
        assert not image.getexif() and "icc_profile" not in image.info
    assert len(normalized) < 262144


@pytest.mark.parametrize("value", ["not base64!", base64.b64encode(b"not an image").decode()])
def test_corrupt_avatar_is_rejected(value: str) -> None:
    with pytest.raises(ApplicationError, match="invalid_avatar"):
        normalize_avatar(IdentityAvatarInput(mime="image/png", data_base64=value))


def test_declared_mime_and_decoded_image_must_match() -> None:
    with pytest.raises(ApplicationError, match="invalid_avatar"):
        normalize_avatar(image_input("image/jpeg"))


def test_oversized_decoded_dimensions_are_rejected() -> None:
    with pytest.raises(ApplicationError, match="invalid_avatar"):
        normalize_avatar(image_input(size=(4097, 1)))


def test_animated_webp_is_rejected() -> None:
    output = BytesIO()
    Image.new("RGB", (20, 20), "red").save(
        output,
        format="WEBP",
        save_all=True,
        append_images=[Image.new("RGB", (20, 20), "blue")],
        duration=100,
        loop=0,
    )
    with pytest.raises(ApplicationError, match="invalid_avatar"):
        normalize_avatar(
            IdentityAvatarInput(
                mime="image/webp", data_base64=base64.b64encode(output.getvalue()).decode()
            )
        )


def test_profile_username_preserves_existing_normalization() -> None:
    assert IdentityProfileInput(username="Reader.Name").username == "reader.name"
