import json

import pytest

from notifications.card import CARD_WIRE_LIMIT_BYTES, SIGNATURE_MARGIN_BYTES, notification_card


@pytest.mark.parametrize("text", ["中文正文" * 50000, '\\"\n' * 50000, "🙂汉字\\\n" * 40000])
def test_card_caps_actual_utf8_json_wire_bytes_with_signature_margin(text):
    card = notification_card(
        title="中文通知标题", text=text, reading_url="https://hotkey.example/items/test"
    )
    encoded = json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(encoded) <= CARD_WIRE_LIMIT_BYTES - SIGNATURE_MARGIN_BYTES
    signed = {**card, "timestamp": "1790985600", "sign": "a" * 44}
    assert (
        len(json.dumps(signed, ensure_ascii=False, separators=(",", ":")).encode())
        <= CARD_WIRE_LIMIT_BYTES
    )
    parsed = json.loads(encoded)
    body = parsed["card"]["elements"][0]["text"]["content"]
    assert "推送仅展示部分" in body and text.startswith(body.split("\n\n推送仅展示部分")[0])
    assert parsed["card"]["elements"][1]["actions"][0]["url"] == "https://hotkey.example/items/test"


def test_short_card_preserves_text_and_rejects_oversized_fixed_fields():
    card = notification_card(
        title="完整摘要", text="正文\n和第二行", reading_url="https://hotkey.example"
    )
    assert card["card"]["elements"][0]["text"]["content"] == "正文\n和第二行"
    with pytest.raises(ValueError):
        notification_card(title="标题" * 50000, text="正文", reading_url="https://hotkey.example")
