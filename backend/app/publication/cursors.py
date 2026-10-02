"""Bounded, scope-bound keyset cursors; cursors never grant material access."""

from __future__ import annotations

import base64
import json
from typing import Any

from core.errors import ApplicationError
from publication.projection import fingerprint


def encode_cursor(scope: dict[str, Any], values: dict[str, Any]) -> str:
    raw = json.dumps(
        {"v": 1, "scope": fingerprint(scope), "values": values}, separators=(",", ":"), default=str
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, scope: dict[str, Any]) -> dict[str, Any]:
    try:
        if not 1 <= len(cursor) <= 4096:
            raise ValueError("invalid length")
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        data = json.loads(raw)
        if (
            data.get("v") != 1
            or data.get("scope") != fingerprint(scope)
            or not isinstance(data.get("values"), dict)
        ):
            raise ValueError("scope mismatch")
        return dict(data["values"])
    except (ValueError, TypeError, KeyError) as error:
        raise ApplicationError("invalid_publication_cursor") from error
