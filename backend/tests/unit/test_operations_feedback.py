import struct

import pytest

from operations.attachments import validate_screenshot
from operations.schemas import FeedbackInput


def test_feedback_rejects_extra_fields_and_whitespace_and_unsafe_page_url():
    from uuid import uuid4

    for data in (
        {"content": "  "},
        {"content": "正常反馈", "owner_id": str(uuid4())},
        {"content": "正常反馈", "page_url": "javascript:alert(1)"},
    ):
        with pytest.raises(ValueError):
            FeedbackInput(operation_id=uuid4(), **data)


def test_image_dimensions_and_magic_are_validated_before_persistence():
    png = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", 20, 10)
        + b"\x08\x06\x00\x00\x00"
        + b"\x00" * 4
        + b"\x00" * 4
        + b"IEND"
        + b"\x00" * 4
    )
    assert validate_screenshot(png, "image/png") == (20, 10)
    with pytest.raises(ValueError):
        validate_screenshot(png, "image/jpeg")
    with pytest.raises(ValueError):
        validate_screenshot(png[:8], "image/png")
    oversized = png[:16] + struct.pack(">II", 20000, 20000) + png[24:]
    with pytest.raises(ValueError):
        validate_screenshot(oversized, "image/png")
