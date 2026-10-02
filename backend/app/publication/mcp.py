"""Five readonly AIHOT tools ported to HotKey's stateless JSON-RPC HTTP endpoint.

Protocol: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
The API layer validates Origin, protocol headers and transport Accept; GET may return 405.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from core.errors import ApplicationError
from publication.application import PublicationApplicationService
from publication.mcp_schemas import (
    CallArguments,
    DailyArguments,
    HotArguments,
    LatestArguments,
    McpError,
    McpRequest,
    McpResponse,
    SearchArguments,
    StoryArguments,
)

_PROTOCOLS = frozenset({"2025-03-26", "2025-06-18"})
_TOOLS = (
    ("hotkey_get_latest", "读取最近24小时或7天公开资讯,保留来源与站内入口", LatestArguments),
    ("hotkey_search", "搜索当前允许公开的资讯;最多6个词并要求全部匹配", SearchArguments),
    (
        "hotkey_get_hot_topics",
        "按真实48小时来源热度读取已确认事件;至少2个参与方且含编辑来源",
        HotArguments,
    ),
    ("hotkey_get_story", "读取确认事件与直接进展,所有固定材料逐项复验公开许可", StoryArguments),
    ("hotkey_get_daily", "读取指定北京日期或最近有效日报;读取不调用模型", DailyArguments),
)


def tools_description() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": description,
            "inputSchema": schema.model_json_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }
        for name, description, schema in _TOOLS
    ]


def validate_transport_headers(
    *, origin: str | None, allowed_origin: str, accept: str, protocol_version: str | None = None
) -> bool:
    return (
        (origin is None or origin.rstrip("/") == allowed_origin.rstrip("/"))
        and ("application/json" in accept and "text/event-stream" in accept)
        and (protocol_version is None or protocol_version in _PROTOCOLS)
    )


class PublicationMcpService:
    def __init__(self, application: PublicationApplicationService) -> None:
        self.application = application

    def transport_allowed(
        self, *, origin: str | None, accept: str, protocol_version: str | None = None
    ) -> bool:
        return validate_transport_headers(
            origin=origin,
            allowed_origin=self.application.origin,
            accept=accept,
            protocol_version=protocol_version,
        )

    def handle(
        self, *, owner_id: UUID, payload: Any, now: datetime | None = None
    ) -> McpResponse | None:
        try:
            request = McpRequest.model_validate(payload)
        except ValidationError:
            identity = (
                payload.get("id")
                if isinstance(payload, dict) and isinstance(payload.get("id"), (str, int))
                else None
            )
            return McpResponse(id=identity, error=McpError(code=-32600, message="Invalid Request"))
        if request.id is None:
            if request.method in {"notifications/initialized", "notifications/cancelled"}:
                return None
            return McpResponse(
                id=None, error=McpError(code=-32600, message="Unsupported notification")
            )
        if request.method == "initialize":
            version = (request.params or {}).get("protocolVersion")
            if not isinstance(version, str):
                return McpResponse(
                    id=request.id, error=McpError(code=-32602, message="Invalid params")
                )
            return McpResponse(
                id=request.id,
                result={
                    "protocolVersion": version if version in _PROTOCOLS else "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "HotKey", "version": "publication-v1"},
                    "instructions": (
                        "Read-only public evidence. Preserve source attribution. "
                        "Native windows 24h/7d; full text stays site-scoped "
                        "unless redistribution is licensed."
                    ),
                },
            )
        if request.method == "ping":
            return McpResponse(id=request.id, result={})
        if request.method == "tools/list":
            return McpResponse(id=request.id, result={"tools": tools_description()})
        if request.method != "tools/call":
            return McpResponse(
                id=request.id, error=McpError(code=-32601, message="Method not found")
            )
        try:
            arguments = CallArguments.model_validate(request.params or {})
            value = self._call(owner_id=owner_id, call=arguments, now=now or datetime.now(UTC))
        except (ValidationError, ValueError):
            return McpResponse(id=request.id, error=McpError(code=-32602, message="Invalid params"))
        except ApplicationError as error:
            return McpResponse(
                id=request.id,
                result={"isError": True, "content": [{"type": "text", "text": error.code}]},
            )
        data = value.model_dump(mode="json")
        return McpResponse(
            id=request.id,
            result={
                "isError": False,
                "structuredContent": data,
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    }
                ],
            },
        )

    def _call(self, *, owner_id: UUID, call: CallArguments, now: datetime) -> BaseModel:
        args = call.arguments
        if call.name == "hotkey_get_latest":
            latest = LatestArguments.model_validate(args)
            return self.application.items(
                owner_id=owner_id,
                window=latest.window,
                mode="selected" if latest.selected else "all",
                limit=latest.limit,
                now=now,
            )
        if call.name == "hotkey_search":
            search = SearchArguments.model_validate(args)
            return self.application.items(
                owner_id=owner_id,
                q=search.q,
                window=search.window,
                mode="selected" if search.selected else "all",
                limit=search.limit,
                now=now,
            )
        if call.name == "hotkey_get_hot_topics":
            hot = HotArguments.model_validate(args)
            return self.application.hot(owner_id=owner_id, limit=hot.limit, now=now)
        if call.name == "hotkey_get_story":
            story = StoryArguments.model_validate(args)
            return self.application.story(owner_id=owner_id, event_id=story.id, now=now)
        if call.name == "hotkey_get_daily":
            daily = DailyArguments.model_validate(args)
            return self.application.edition(
                owner_id=owner_id, kind="daily", key=daily.date, now=now
            )
        raise ValueError("Unknown tool")
