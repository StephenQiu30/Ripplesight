import base64
from io import BytesIO

import pytest
from PIL import Image

from core.errors import ApplicationError
from operations.site_schemas import ContactImageInput
from operations.site_services import normalize_contact_image


def test_contact_image_decodes_actual_pixels_and_removes_trailing_metadata() -> None:
    stream = BytesIO()
    Image.new("RGB", (20, 20), "white").save(stream, format="PNG")
    encoded = normalize_contact_image(
        ContactImageInput(
            mime="image/png",
            data_base64=base64.b64encode(stream.getvalue() + b"private tail").decode(),
        )
    )
    assert b"private tail" not in encoded
    with Image.open(BytesIO(encoded)) as loaded:
        loaded.load()
        assert loaded.size == (20, 20) and loaded.format == "PNG"


def test_contact_image_rejects_truncated_image_wrong_mime_and_oversized_pixels() -> None:
    stream = BytesIO()
    Image.new("RGB", (4096, 1024), "white").save(stream, format="PNG")
    for data, mime in ((stream.getvalue(), "image/png"), (b"PNG incomplete", "image/png")):
        with pytest.raises(ApplicationError, match="invalid_operations_input"):
            normalize_contact_image(
                ContactImageInput(
                    mime=mime,
                    data_base64=base64.b64encode(data).decode(),  # type: ignore[arg-type]
                )
            )
    stream = BytesIO()
    Image.new("RGB", (20, 20), "white").save(stream, format="PNG")
    with pytest.raises(ApplicationError, match="invalid_operations_input"):
        normalize_contact_image(
            ContactImageInput(
                mime="image/jpeg", data_base64=base64.b64encode(stream.getvalue()).decode()
            )
        )
