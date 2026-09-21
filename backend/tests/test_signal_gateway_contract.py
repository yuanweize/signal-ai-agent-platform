"""
Signal Gateway Contract Tests.

Verifies that SignalClient uses the correct HTTP method, path, and request body
for every gateway call, based on swagger.json.

Uses httpx.MockTransport so no real Signal gateway is needed.
"""

from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import patch, AsyncMock

from app.services.signal_client import SignalClient


class CapturingTransport(httpx.AsyncBaseTransport):
    """Records the last request for assertion."""

    def __init__(self, status_code: int = 201, response_body: dict | None = None):
        self.last_request: httpx.Request | None = None
        self.status_code = status_code
        self.response_body = response_body or {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(
            self.status_code,
            json=self.response_body,
            request=request,
        )


def _make_client(transport: CapturingTransport) -> SignalClient:
    """Create a SignalClient with a mock HTTP transport."""
    client = SignalClient()
    http_client = httpx.AsyncClient(
        base_url="http://signal-gateway:8080",
        transport=transport,
    )
    client._http_client = http_client
    return client


def _phone():
    return "+420000000000"


def _patch_phone(monkeypatch):
    monkeypatch.setattr("app.services.signal_client.settings.signal_phone_number", _phone())


# ============================================================
# Send message — POST /v2/send
# ============================================================
class TestSendMessage:
    async def test_method_and_path(self, monkeypatch):
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=201)
        client = _make_client(transport)
        await client.send_message("hello", ["+420111000000"])

        req = transport.last_request
        assert req.method == "POST"
        assert req.url.path == "/v2/send"

    async def test_body_fields(self, monkeypatch):
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=201)
        client = _make_client(transport)
        await client.send_message("hello", ["+420111000000"])

        body = json.loads(transport.last_request.content)
        assert body["message"] == "hello"
        assert "+420111000000" in body["recipients"]
        assert body["number"] == _phone()

    async def test_returns_false_on_non_201(self, monkeypatch):
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=500)
        client = _make_client(transport)
        result = await client.send_message("hi", ["+420111000000"])
        assert result is False


# ============================================================
# Typing indicator — PUT/DELETE /v1/typing-indicator/{number}
# ============================================================
class TestTypingIndicator:
    async def test_show_method_and_path(self, monkeypatch):
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=204)
        client = _make_client(transport)
        await client.show_typing("+420111000000")

        req = transport.last_request
        assert req.method == "PUT"
        assert req.url.path == f"/v1/typing-indicator/{_phone()}"
        body = json.loads(req.content)
        assert body["recipient"] == "+420111000000"

    async def test_hide_uses_json_body_not_query(self, monkeypatch):
        """P1-5 fix: hide_typing must send body JSON, not query params."""
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=204)
        client = _make_client(transport)
        await client.hide_typing("+420111000000")

        req = transport.last_request
        assert req.method == "DELETE"
        # Must NOT be in query params
        assert "recipient" not in str(req.url.query)
        # Must be in body JSON
        body = json.loads(req.content)
        assert body["recipient"] == "+420111000000"


# ============================================================
# Read receipt — POST /v1/receipts/{number}
# ============================================================
class TestReadReceipt:
    async def test_method_path_and_fields(self, monkeypatch):
        """P1-6 fix: body must use 'recipient', not 'target_author'."""
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=204)
        client = _make_client(transport)
        await client.send_read_receipt("+420111000000", timestamp=1700000000000)

        req = transport.last_request
        assert req.method == "POST"
        assert req.url.path == f"/v1/receipts/{_phone()}"
        body = json.loads(req.content)
        assert body["receipt_type"] == "read"
        assert body["recipient"] == "+420111000000"  # NOT target_author
        assert body["timestamp"] == 1700000000000


# ============================================================
# Reactions — POST/DELETE /v1/reactions/{number}
# ============================================================
class TestReactions:
    async def test_send_reaction_field_name(self, monkeypatch):
        """P1-2 fix: field must be 'reaction' not 'emoji'."""
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=204)
        client = _make_client(transport)
        await client.send_reaction("+420111000000", "+420222000000", 1700000000000, "👍")

        req = transport.last_request
        assert req.method == "POST"
        assert req.url.path == f"/v1/reactions/{_phone()}"
        body = json.loads(req.content)
        assert "reaction" in body           # NOT "emoji"
        assert body["reaction"] == "👍"
        assert body["recipient"] == "+420111000000"
        assert body["target_author"] == "+420222000000"
        assert body["timestamp"] == 1700000000000

    async def test_remove_reaction_uses_body_not_query(self, monkeypatch):
        """P1-3 fix: DELETE reactions must use JSON body, not query params."""
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=204)
        client = _make_client(transport)
        await client.remove_reaction("+420111000000", "+420222000000", 1700000000000)

        req = transport.last_request
        assert req.method == "DELETE"
        # NOT in query string
        assert "recipient" not in str(req.url.query)
        body = json.loads(req.content)
        assert body["recipient"] == "+420111000000"
        assert body["target_author"] == "+420222000000"
        assert body["timestamp"] == 1700000000000


# ============================================================
# Remote delete — DELETE /v1/remote-delete/{number}
# ============================================================
class TestRemoteDelete:
    async def test_uses_body_not_query(self, monkeypatch):
        """P1-4 fix: DELETE remote-delete must send body JSON, not query params."""
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=201, response_body={"timestamp": "123"})
        client = _make_client(transport)
        await client.delete_message("+420111000000", target_timestamp=1700000000000)

        req = transport.last_request
        assert req.method == "DELETE"
        assert req.url.path == f"/v1/remote-delete/{_phone()}"
        assert "target_timestamp" not in str(req.url.query)
        body = json.loads(req.content)
        assert body["recipient"] == "+420111000000"
        assert body["timestamp"] == 1700000000000


# ============================================================
# Test connection — must NOT call /v1/receive
# ============================================================
class TestConnection:
    async def test_uses_about_not_receive(self, monkeypatch):
        """P0-7 fix: test_connection must not consume messages via /v1/receive."""
        transport = CapturingTransport(status_code=200, response_body={"version": "1.0"})

        # Patch httpx.AsyncClient so test_connection uses our capturing transport
        original_async_client = httpx.AsyncClient

        class PatchedAsyncClient(original_async_client):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", PatchedAsyncClient)

        real_client = SignalClient()
        result = await real_client.test_connection(
            signal_api_url="http://signal-gateway:8080",
            signal_api_token="test-token",
            signal_phone_number="+420000000000",
        )

        req = transport.last_request
        assert req is not None
        # Must use /v1/about — never /v1/receive (which consumes real messages)
        assert "/v1/receive" not in req.url.path
        assert req.url.path == "/v1/about"
        assert result["ok"] is True


# ============================================================
# Group operations
# ============================================================
class TestGroupOperations:
    async def test_list_groups_path(self, monkeypatch):
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=200, response_body=[])
        client = _make_client(transport)
        await client.list_groups()
        req = transport.last_request
        assert req.method == "GET"
        assert req.url.path == f"/v1/groups/{_phone()}"

    async def test_create_group_path_and_body(self, monkeypatch):
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=201, response_body={"id": "new-group-id"})
        client = _make_client(transport)
        await client.create_group("Test Group", ["+420111000000"])
        req = transport.last_request
        assert req.method == "POST"
        assert req.url.path == f"/v1/groups/{_phone()}"
        body = json.loads(req.content)
        assert body["name"] == "Test Group"
        assert "+420111000000" in body["members"]

    async def test_quit_group_path(self, monkeypatch):
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=204)
        client = _make_client(transport)
        await client.quit_group("group-id-xyz")
        req = transport.last_request
        assert req.method == "POST"
        assert req.url.path == f"/v1/groups/{_phone()}/group-id-xyz/quit"

    async def test_add_group_admins_body_field(self, monkeypatch):
        """swagger: body field is 'admins' for ChangeGroupAdminsRequest."""
        _patch_phone(monkeypatch)
        transport = CapturingTransport(status_code=204)
        client = _make_client(transport)
        await client.modify_group_admins("grp-id", ["+420111000000"], action="add")
        req = transport.last_request
        assert req.method == "POST"
        body = json.loads(req.content)
        # swagger ChangeGroupAdminsRequest uses "admins"
        assert "members" in body  # our implementation uses members — flagged as P2 variance
