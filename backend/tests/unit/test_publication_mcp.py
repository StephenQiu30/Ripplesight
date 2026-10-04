from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from publication.application import PublicationApplicationService
from publication.mcp import PublicationMcpService, tools_description, validate_transport_headers
from publication.schemas import PublicItemsPage

NOW = datetime(2026, 10, 2, tzinfo=UTC)


class ControlledReading:
    origin = "https://hotkey.example"

    def __init__(self):
        self.calls = []

    def items(self, **options):
        self.calls.append(options)
        return PublicItemsPage(items=[], next_cursor=None, snapshot_at=NOW)


def test_five_tools_are_readonly_and_never_offer_fetching_or_write_capabilities() -> None:
    tools = tools_description()
    assert [tool["name"] for tool in tools] == [
        "hotkey_get_latest",
        "hotkey_search",
        "hotkey_get_hot_topics",
        "hotkey_get_story",
        "hotkey_get_daily",
    ]
    assert all(
        tool["annotations"]["readOnlyHint"] and not tool["annotations"]["destructiveHint"]
        for tool in tools
    )
    controlled = ControlledReading()
    service = PublicationMcpService(cast(PublicationApplicationService, controlled))
    response = service.handle(
        owner_id=uuid4(),
        payload={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "hotkey_get_latest", "arguments": {}},
        },
        now=NOW,
    )
    assert response and response.result and not response.result["isError"]
    assert response.result["structuredContent"]["items"] == []
    assert controlled.calls[0]["window"] == "24h" and controlled.calls[0]["mode"] == "selected"
    assert (
        service.handle(
            owner_id=uuid4(), payload={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        is None
    )


def test_protocol_negotiation_and_transport_origin_accept_validation() -> None:
    service = PublicationMcpService(cast(PublicationApplicationService, ControlledReading()))
    response = service.handle(
        owner_id=uuid4(),
        payload={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )
    assert response.result["protocolVersion"] == "2025-06-18"
    assert validate_transport_headers(
        origin=None,
        allowed_origin="https://hotkey.example",
        accept="application/json, text/event-stream",
    )
    assert not validate_transport_headers(
        origin="https://attacker.example",
        allowed_origin="https://hotkey.example",
        accept="application/json, text/event-stream",
    )
    assert not validate_transport_headers(
        origin=None, allowed_origin="https://hotkey.example", accept="application/json"
    )
    assert not validate_transport_headers(
        origin=None,
        allowed_origin="https://hotkey.example",
        accept="application/json,text/event-stream",
        protocol_version="bad",
    )


def test_malformed_requests_and_unknown_tools_do_not_execute_any_reading() -> None:
    controlled = ControlledReading()
    service = PublicationMcpService(cast(PublicationApplicationService, controlled))
    bad_payloads = [
        {},
        [],
        {"jsonrpc": "2.0", "id": True, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": {}}},
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "fetch_url", "arguments": {"url": "http://127.0.0.1"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "hotkey_get_latest", "arguments": {"window": "30d"}},
        },
    ]
    for payload in bad_payloads:
        response = service.handle(owner_id=uuid4(), payload=payload)
        assert response and response.error and response.error.code in {-32600, -32602}
    assert not controlled.calls


def test_cursor_and_public_search_permission_scope_reach_same_reader() -> None:
    controlled = ControlledReading()
    service = PublicationMcpService(cast(PublicationApplicationService, controlled))
    for name, args in (
        ("hotkey_get_latest", {"cursor": "bounded-next"}),
        ("hotkey_search", {"q": "模型", "cursor": "bounded-next"}),
    ):
        result = service.handle(
            owner_id=uuid4(),
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            },
            redistribute=True,
        )
        assert result and result.result and not result.result["isError"]
        assert controlled.calls[-1]["cursor"] == "bounded-next"
    assert controlled.calls[-1]["redistribute"] is True


def test_oversized_mcp_input_and_cursor_never_execute_reader() -> None:
    controlled = ControlledReading()
    service = PublicationMcpService(cast(PublicationApplicationService, controlled))
    for payload in (
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"x": "x" * 17000}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "hotkey_get_latest", "arguments": {"cursor": "x" * 4097}},
        },
    ):
        result = service.handle(owner_id=uuid4(), payload=payload)
        assert result and result.error and result.error.code in {-32600, -32602}
    assert controlled.calls == []
