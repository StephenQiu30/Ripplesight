"""Conservative wire-byte cap for signed Feishu interactive notifications."""

import json

CARD_WIRE_LIMIT_BYTES = 18 * 1024
SIGNATURE_MARGIN_BYTES = 512
_PARTIAL = "\n\n推送仅展示部分,请阅读全文。"


def notification_card(*, title: str, text: str, reading_url: str) -> dict[str, object]:
    def build(body: str) -> dict[str, object]:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": body}},
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "查看完整内容"},
                                "type": "primary",
                                "url": reading_url,
                            }
                        ],
                    },
                ],
            },
        }

    def fits(body: str) -> bool:
        encoded = json.dumps(build(body), ensure_ascii=False, separators=(",", ":")).encode()
        return len(encoded) <= CARD_WIRE_LIMIT_BYTES - SIGNATURE_MARGIN_BYTES

    if fits(text):
        return build(text)
    if not fits(_PARTIAL):
        raise ValueError("notification card fixed fields exceed the wire byte cap")
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if fits(text[:middle] + _PARTIAL):
            low = middle
        else:
            high = middle - 1
    return build(text[:low] + _PARTIAL)
