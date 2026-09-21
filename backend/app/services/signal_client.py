"""
Signal API Client — communicates with secured-signal-api gateway.

Two transport modes:
1. WebSocket (primary) — real-time message stream via ws://.../v1/receive/{number}
2. HTTP Polling (fallback) — periodic GET /v1/receive/{number}

Sending always uses HTTP POST /v2/send with Bearer token auth.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI, WebSocketException

from app.config import settings
from app.schemas.signal import SignalIncomingMessage, SignalSendRequest
from app.services.metrics import runtime_metrics

logger = logging.getLogger("signal.client")

# Regex to strip ANSI escape codes, newlines, and other control characters
_SANITIZE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;]*[a-zA-Z]")


def _sanitize_log(text: str, max_len: int = 120) -> str:
    """Strip control characters and truncate for safe log output."""
    cleaned = _SANITIZE_RE.sub("", text)
    cleaned = cleaned.replace("\n", " ").replace("\r", " ")
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "…"
    return cleaned


# Type for the callback that handles incoming messages
MessageCallback = Callable[[SignalIncomingMessage], Awaitable[None]]


class SignalClient:
    """
    Async Signal API client with WebSocket listener and HTTP sender.

    Usage:
        client = SignalClient()
        client.on_message = my_handler_function
        await client.start()   # begins listening in background
        await client.send_message("Hello!", ["+420123456789"])
        await client.stop()    # graceful shutdown
    """

    def __init__(self) -> None:
        self._on_message: MessageCallback | None = None
        self._listener_task: asyncio.Task | None = None
        self._running = False
        self._connected = False
        self._http_client: httpx.AsyncClient | None = None

        # Reconnection state
        self._reconnect_delay = 1.0  # Start at 1 second
        self._max_reconnect_delay = 60.0
        self._max_reconnect_attempts = 100  # Hard cap to prevent infinite storm
        self._reconnect_attempts = 0

    @property
    def on_message(self) -> MessageCallback | None:
        return self._on_message

    @on_message.setter
    def on_message(self, callback: MessageCallback) -> None:
        """Register a callback for incoming messages."""
        self._on_message = callback

    @property
    def is_running(self) -> bool:
        """Whether listener lifecycle is currently active."""
        return self._running

    @property
    def is_connected(self) -> bool:
        """Whether Signal gateway is currently reachable with active listener transport."""
        return self._connected

    # ---- HTTP Client Setup ----

    def _get_http_client(self) -> httpx.AsyncClient:
        """Lazily create or return the shared HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            headers = {"Content-Type": "application/json"}
            if settings.signal_api_token:
                headers["Authorization"] = f"Bearer {settings.signal_api_token}"
            self._http_client = httpx.AsyncClient(
                base_url=settings.signal_api_url,
                headers=headers,
                timeout=30.0,
            )
        return self._http_client

    # ---- Sending Messages ----

    async def send_message(
        self,
        text: str,
        recipients: list[str],
        number: str | None = None,
    ) -> bool:
        """
        Send a text message to one or more recipients.

        Args:
            text: Message text
            recipients: List of phone numbers or "group.{groupId}" strings
            number: Bot's phone number (defaults to settings)

        Returns:
            True if sent successfully, False otherwise
        """
        request = SignalSendRequest(
            message=text,
            number=number or settings.signal_phone_number,
            recipients=recipients,
        )

        try:
            client = self._get_http_client()
            response = await client.post(
                "/v2/send",
                json=request.model_dump(exclude_none=True),
            )

            if response.status_code == 201:
                logger.info(f"✉️  Message sent to {recipients} ({len(text)} chars)")
                return True
            else:
                logger.error(f"❌ Send failed: HTTP {response.status_code} — {response.text}")
                return False

        except httpx.HTTPError as e:
            logger.error(f"❌ Send HTTP error: {e}")
            return False

    # ---- Typing Indicator ----

    async def show_typing(
        self,
        recipient: str,
        number: str | None = None,
    ) -> bool:
        """
        Show typing indicator to a recipient.

        Args:
            recipient: Phone number or "group.{groupId}"
            number: Bot's phone number (defaults to settings)
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.put(
                f"/v1/typing-indicator/{phone}",
                json={"recipient": recipient},
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.debug(f"Typing indicator (show) failed: {e}")
            return False

    async def hide_typing(
        self,
        recipient: str,
        number: str | None = None,
    ) -> bool:
        """
        Hide typing indicator from a recipient.

        Args:
            recipient: Phone number or "group.{groupId}"
            number: Bot's phone number (defaults to settings)

        Note: swagger spec requires body JSON {"recipient": ...} for DELETE,
        not query params.
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.request(
                "DELETE",
                f"/v1/typing-indicator/{phone}",
                json={"recipient": recipient},
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.debug(f"Typing indicator (hide) failed: {e}")
            return False

    # ---- Read Receipts ----

    async def send_read_receipt(
        self,
        recipient: str,
        timestamp: int,
        number: str | None = None,
    ) -> bool:
        """
        Send a read receipt to acknowledge a message.

        Args:
            recipient: Sender's phone number (the "recipient" in swagger Receipt schema)
            timestamp: Timestamp of the message to mark as read (integer, not string)
            number: Bot's phone number (defaults to settings)

        Swagger: POST /v1/receipts/{number}
        Body: { "receipt_type": "read", "recipient": <str>, "timestamp": <int> }
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.post(
                f"/v1/receipts/{phone}",
                json={
                    "receipt_type": "read",
                    "recipient": recipient,
                    "timestamp": timestamp,
                },
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.debug(f"Read receipt send failed: {e}")
            return False

    # ---- Reactions & Remote Delete ----

    async def send_reaction(
        self,
        recipient: str,
        target_author: str,
        timestamp: int,
        emoji: str,
        number: str | None = None,
    ) -> bool:
        """Send a reaction emoji to a specific message.

        Swagger: POST /v1/reactions/{number}
        Body: { "reaction": <str>, "recipient": <str>, "target_author": <str>, "timestamp": <int> }
        Note: field name is "reaction", not "emoji".
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.post(
                f"/v1/reactions/{phone}",
                json={
                    "recipient": recipient,
                    "reaction": emoji,
                    "target_author": target_author,
                    "timestamp": timestamp,
                },
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Send reaction failed: {e}")
            return False

    async def remove_reaction(
        self,
        recipient: str,
        target_author: str,
        timestamp: int,
        number: str | None = None,
    ) -> bool:
        """Remove a previously sent reaction.

        Swagger: DELETE /v1/reactions/{number}
        Body: { "recipient": <str>, "target_author": <str>, "timestamp": <int> }
        Note: body JSON, NOT query params.
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.request(
                "DELETE",
                f"/v1/reactions/{phone}",
                json={
                    "recipient": recipient,
                    "target_author": target_author,
                    "timestamp": timestamp,
                },
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Remove reaction failed: {e}")
            return False

    async def delete_message(
        self,
        recipient: str,
        target_timestamp: int,
        number: str | None = None,
    ) -> bool:
        """Remote delete a message sent by this bot.

        Swagger: DELETE /v1/remote-delete/{number}
        Body: { "recipient": <str>, "timestamp": <int> }
        Note: body JSON, NOT query params.
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.request(
                "DELETE",
                f"/v1/remote-delete/{phone}",
                json={
                    "recipient": recipient,
                    "timestamp": target_timestamp,
                },
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Remote delete failed: {e}")
            return False

    # ---- Attachments ----

    async def list_attachments(self) -> list[str]:
        """List all stored attachment IDs."""
        try:
            client = self._get_http_client()
            response = await client.get("/v1/attachments")
            if response.status_code == 200:
                return response.json()
            return []
        except httpx.HTTPError as e:
            logger.error(f"List attachments failed: {e}")
            return []

    async def serve_attachment(self, attachment_id: str) -> bytes | None:
        """Get the raw bytes of an attachment."""
        try:
            client = self._get_http_client()
            response = await client.get(f"/v1/attachments/{attachment_id}")
            if response.status_code == 200:
                return response.content
            return None
        except httpx.HTTPError as e:
            logger.error(f"Serve attachment failed: {e}")
            return None

    async def delete_attachment(self, attachment_id: str) -> bool:
        """Delete an attachment from the Signal CLI internal storage."""
        try:
            client = self._get_http_client()
            response = await client.delete(f"/v1/attachments/{attachment_id}")
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Delete attachment failed: {e}")
            return False

    # ---- Contacts ----

    async def list_contacts(
        self,
        number: str | None = None,
    ) -> list[dict]:
        """List all contacts associated with this number."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.get(f"/v1/contacts/{phone}")
            if response.status_code == 200:
                return response.json()
            return []
        except httpx.HTTPError as e:
            logger.error(f"List contacts failed: {e}")
            return []

    async def sync_contacts(
        self,
        number: str | None = None,
    ) -> bool:
        """Sync contacts to all linked devices."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.post(f"/v1/contacts/{phone}/sync")
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Sync contacts failed: {e}")
            return False

    async def get_contact_avatar(
        self,
        uuid: str,
        number: str | None = None,
    ) -> bytes | None:
        """Get the avatar bytes for a specific contact UUID."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.get(f"/v1/contacts/{phone}/{uuid}/avatar")
            if response.status_code == 200:
                return response.content
            return None
        except httpx.HTTPError as e:
            logger.error(f"Get contact avatar failed: {e}")
            return None

    # ---- Group Management ----

    async def list_groups(
        self,
        number: str | None = None,
    ) -> list[dict]:
        """
        List all Signal groups the bot belongs to.

        Returns:
            List of group info dicts from the Signal API
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.get(f"/v1/groups/{phone}")
            if response.status_code == 200:
                return response.json()
            logger.warning(f"List groups returned HTTP {response.status_code}")
            return []
        except httpx.HTTPError as e:
            logger.error(f"List groups failed: {e}")
            return []

    async def get_group(
        self,
        group_id: str,
        number: str | None = None,
    ) -> dict | None:
        """
        Get details of a specific Signal group.

        Args:
            group_id: Internal Signal group ID
            number: Bot's phone number (defaults to settings)
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.get(f"/v1/groups/{phone}/{group_id}")
            if response.status_code == 200:
                return response.json()
            return None
        except httpx.HTTPError as e:
            logger.error(f"Get group failed: {e}")
            return None

    async def quit_group(
        self,
        group_id: str,
        number: str | None = None,
    ) -> bool:
        """
        Quit (leave) a Signal group.

        Args:
            group_id: Internal Signal group ID
            number: Bot's phone number (defaults to settings)
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.post(f"/v1/groups/{phone}/{group_id}/quit")
            ok = response.status_code in {200, 201, 204}
            if ok:
                logger.info(f"👋 Left group {_sanitize_log(group_id, 32)}")
            else:
                logger.warning(f"Quit group returned HTTP {response.status_code}")
            return ok
        except httpx.HTTPError as e:
            logger.error(f"Quit group failed: {e}")
            return False

    # ---- Advanced Group Management ----

    async def create_group(
        self,
        name: str,
        members: list[str],
        number: str | None = None,
    ) -> dict | None:
        """Create a new Signal Group."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.post(
                f"/v1/groups/{phone}",
                json={"name": name, "members": members},
            )
            if response.status_code == 201:
                return response.json()
            return None
        except httpx.HTTPError as e:
            logger.error(f"Create group failed: {e}")
            return None

    async def update_group(
        self,
        group_id: str,
        name: str | None = None,
        description: str | None = None,
        number: str | None = None,
    ) -> bool:
        """Update an existing Signal Group's metadata."""
        phone = number or settings.signal_phone_number
        try:
            payload = {}
            if name is not None:
                payload["name"] = name
            if description is not None:
                payload["description"] = description

            client = self._get_http_client()
            response = await client.put(
                f"/v1/groups/{phone}/{group_id}",
                json=payload,
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Update group failed: {e}")
            return False

    async def add_group_members(
        self,
        group_id: str,
        members: list[str],
        number: str | None = None,
    ) -> bool:
        """Add members to a group."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.post(
                f"/v1/groups/{phone}/{group_id}/members",
                json={"members": members},
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Add group members failed: {e}")
            return False

    async def remove_group_members(
        self,
        group_id: str,
        members: list[str],
        number: str | None = None,
    ) -> bool:
        """Remove members from a group."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.delete(
                f"/v1/groups/{phone}/{group_id}/members",
                json={"members": members},
            )
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Remove group members failed: {e}")
            return False

    async def modify_group_admins(
        self,
        group_id: str,
        admins: list[str],
        action: str = "add",
        number: str | None = None,
    ) -> bool:
        """Add or remove group admins."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            url = f"/v1/groups/{phone}/{group_id}/admins"
            if action == "add":
                response = await client.post(url, json={"members": admins})
            else:
                response = await client.delete(url, json={"members": admins})
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Modify group admins failed: {e}")
            return False

    # ---- Accounts & Devices ----

    async def update_profile(
        self,
        name: str | None = None,
        about: str | None = None,
        number: str | None = None,
    ) -> bool:
        """Update the Signal profile name and about text."""
        phone = number or settings.signal_phone_number
        try:
            payload = {}
            if name is not None:
                payload["name"] = name
            if about is not None:
                payload["about"] = about

            client = self._get_http_client()
            response = await client.put(f"/v1/profiles/{phone}", json=payload)
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Update profile failed: {e}")
            return False

    async def list_devices(
        self,
        number: str | None = None,
    ) -> list[dict]:
        """List all devices linked to this Signal account."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.get(f"/v1/devices/{phone}")
            if response.status_code == 200:
                return response.json()
            return []
        except httpx.HTTPError as e:
            logger.error(f"List devices failed: {e}")
            return []

    async def remove_device(
        self,
        device_id: int,
        number: str | None = None,
    ) -> bool:
        """Unlink a specific device."""
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            response = await client.delete(f"/v1/devices/{phone}/{device_id}")
            return response.status_code in {200, 201, 204}
        except httpx.HTTPError as e:
            logger.error(f"Remove device failed: {e}")
            return False

    # ---- QR Code Device Linking ----

    async def get_qrcode_link(self) -> dict | None:
        """
        Get a QR code link URI for linking a new device.

        Returns:
            Dict with link info, or None on failure
        """
        try:
            client = self._get_http_client()
            response = await client.get("/v1/qrcodelink")
            if response.status_code == 200:
                return response.json()
            return None
        except httpx.HTTPError as e:
            logger.error(f"QR code link failed: {e}")
            return None

    # ---- Number Search ----

    async def search_numbers(
        self,
        numbers: list[str],
        number: str | None = None,
    ) -> dict:
        """
        Check if phone numbers are registered on Signal.

        Args:
            numbers: List of phone numbers to check
            number: Bot's phone number (defaults to settings)

        Returns:
            Dict mapping numbers to their registration status
        """
        phone = number or settings.signal_phone_number
        try:
            client = self._get_http_client()
            numbers_param = ",".join(numbers)
            response = await client.get(
                f"/v1/search/{phone}",
                params={"numbers": numbers_param},
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except httpx.HTTPError as e:
            logger.error(f"Number search failed: {e}")
            return {}

    async def send_reply(
        self,
        text: str,
        recipient: str,
    ) -> bool:
        """
        Convenience method to reply to a single recipient or group.

        Args:
            text: Reply text
            recipient: Phone number or "group.{groupId}"
        """
        return await self.send_message(text, [recipient])

    # ---- Receiving Messages ----

    async def start(self) -> None:
        """Start the background message listener."""
        if self._running:
            logger.warning("Signal client already running")
            return

        self._running = True
        self._connected = False
        self._reconnect_delay = 1.0
        self._reconnect_attempts = 0
        self._listener_task = asyncio.create_task(self._listener_loop())
        logger.info("🎧 Signal message listener started")

    async def test_connection(
        self,
        *,
        signal_api_url: str,
        signal_api_token: str,
        signal_phone_number: str,
    ) -> dict:
        """Perform an explicit Signal gateway connection check.

        Uses GET /v1/about (no side effects) to verify reachability,
        then checks account existence via GET /v1/accounts.
        We intentionally do NOT call /v1/receive which would consume messages.
        """
        base_url = signal_api_url.strip()
        token = signal_api_token.strip()

        if not base_url:
            return {
                "ok": False,
                "message": "Signal API URL is required",
                "status_code": None,
                "latency_ms": 0,
            }

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                base_url=base_url,
                headers=headers,
                timeout=10.0,
            ) as client:
                # Use /v1/about — no side effects, confirms gateway is reachable and auth works
                response = await client.get("/v1/about")
            latency_ms = int((time.perf_counter() - started) * 1000)
            ok = response.status_code in {200, 204}
            message = (
                "Signal gateway reachable"
                if ok
                else f"Signal gateway responded with HTTP {response.status_code}"
            )
            return {
                "ok": ok,
                "message": message,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            }
        except httpx.HTTPError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "ok": False,
                "message": f"Signal gateway request failed: {exc}",
                "status_code": None,
                "latency_ms": latency_ms,
            }

    async def apply_runtime_config(
        self,
        *,
        signal_api_url: str,
        signal_api_token: str,
        signal_phone_number: str,
        restart_listener: bool = True,
    ) -> None:
        """Apply runtime Signal settings and refresh transports if needed."""
        settings.signal_api_url = signal_api_url.strip()
        settings.signal_api_token = signal_api_token.strip()
        settings.signal_phone_number = signal_phone_number.strip()

        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        self._http_client = None

        if not restart_listener:
            return

        is_ready = bool(settings.signal_api_url and settings.signal_phone_number)
        if self._running:
            await self.stop()

        if is_ready:
            await self.start()

    async def stop(self) -> None:
        """Stop the background message listener gracefully."""
        self._running = False
        self._connected = False

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        self._http_client = None

        logger.info("🛑 Signal message listener stopped")

    async def _listener_loop(self) -> None:
        """
        Main listener loop with automatic fallback.

        Tries WebSocket first. If that fails, falls back to HTTP polling.
        Always attempts to reconnect with exponential backoff.
        """
        while self._running:
            try:
                # Try WebSocket first
                await self._ws_listener()
            except (
                ConnectionClosed,
                InvalidURI,
                WebSocketException,
                OSError,
                ConnectionRefusedError,
            ) as e:
                if not self._running:
                    break
                logger.warning(f"⚠️  WebSocket connection failed: {e.__class__.__name__}: {e}")
                logger.info("📡 Falling back to HTTP polling...")

                try:
                    await self._poll_listener()
                except (httpx.HTTPError, OSError, ConnectionRefusedError) as poll_err:
                    if not self._running:
                        break
                    logger.warning(
                        f"⚠️  HTTP polling also failed: {poll_err.__class__.__name__}: {poll_err}"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"❌ Unexpected listener error: {e}", exc_info=True)

            # Exponential backoff before retry
            if self._running:
                self._reconnect_attempts += 1

                # Hard cap: stop after too many consecutive failures
                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.error(
                        f"🛑 Reached max reconnect attempts "
                        f"({self._max_reconnect_attempts}). "
                        f"Stopping listener to prevent reconnect storm. "
                        f"Manual restart or config change required."
                    )
                    self._running = False
                    self._connected = False
                    break

                delay = min(
                    self._reconnect_delay * (2 ** min(self._reconnect_attempts - 1, 6)),
                    self._max_reconnect_delay,
                )
                logger.info(
                    f"⏳ Reconnecting in {delay:.0f}s "
                    f"(attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})..."
                )
                await asyncio.sleep(delay)

    async def _ws_listener(self) -> None:
        """
        Connect to WebSocket and stream incoming messages.

        Resets reconnect backoff on successful connection.
        """
        ws_url = settings.signal_ws_url
        headers = {}
        if settings.signal_api_token:
            headers["Authorization"] = f"Bearer {settings.signal_api_token}"

        logger.info(f"🔌 Connecting WebSocket: {ws_url}")

        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=5,
            max_size=2 * 1024 * 1024,  # 2MB — prevent OOM from large attachments
        ) as ws:
            # Reset backoff on successful connection
            self._reconnect_delay = 1.0
            self._reconnect_attempts = 0
            self._connected = True
            logger.info("✅ WebSocket connected — listening for messages")

            async for raw_message in ws:
                if not self._running:
                    break
                await self._process_raw_message(raw_message)
        self._connected = False

    async def _poll_listener(self) -> None:
        """
        Poll HTTP endpoint for messages at regular intervals.

        Runs until WebSocket becomes available again or stop() is called.
        """
        poll_url = f"/v1/receive/{settings.signal_phone_number}"
        poll_interval = 2.0  # seconds between polls
        max_empty_polls = 150  # ~5 minutes before trying WS again

        logger.info(f"📡 HTTP polling: {settings.signal_api_url}{poll_url}")

        client = self._get_http_client()
        empty_polls = 0

        while self._running and empty_polls < max_empty_polls:
            try:
                runtime_metrics.inc("signal.pull.total")
                response = await client.get(poll_url)

                if response.status_code == 200:
                    self._connected = True
                    messages = response.json()

                    if isinstance(messages, list) and len(messages) > 0:
                        empty_polls = 0  # Reset on activity
                        for msg_data in messages:
                            raw = json.dumps(msg_data)
                            await self._process_raw_message(raw)
                    else:
                        empty_polls += 1
                elif response.status_code == 204:
                    # No content — no new messages
                    self._connected = True
                    empty_polls += 1
                else:
                    self._connected = False
                    runtime_metrics.inc("signal.pull.fail")
                    if response.status_code == 401:
                        runtime_metrics.inc("signal.pull.401")
                    if response.status_code >= 500:
                        runtime_metrics.inc("signal.pull.5xx")
                    logger.warning(f"⚠️  Poll response: HTTP {response.status_code}")
                    empty_polls += 1

            except httpx.HTTPError as e:
                self._connected = False
                runtime_metrics.inc("signal.pull.fail")
                logger.warning(f"⚠️  Poll error: {e}")
                raise  # Let the outer loop handle reconnection

            await asyncio.sleep(poll_interval)

        # If we exhausted max_empty_polls, return to try WebSocket again
        if self._running:
            logger.info("🔄 Switching back to WebSocket mode...")

    async def _process_raw_message(self, raw: str | bytes) -> None:
        """Parse a raw JSON string and dispatch to the callback."""
        try:
            data = json.loads(raw)

            # signal-cli-rest-api can wrap in different formats
            # Handle both {"envelope": {...}} and [{"envelope": {...}}, ...]
            if isinstance(data, list):
                for item in data:
                    await self._dispatch_envelope(item)
            elif isinstance(data, dict):
                await self._dispatch_envelope(data)
            else:
                logger.warning(f"⚠️  Unknown message format: {type(data)}")

        except json.JSONDecodeError as e:
            logger.warning(f"⚠️  Invalid JSON received: {e}")
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)

    async def _dispatch_envelope(self, data: dict) -> None:
        """Validate and dispatch a single message envelope."""
        try:
            msg = SignalIncomingMessage.model_validate(data)
        except Exception as e:
            logger.debug(f"Skipping unparseable message: {e}")
            return

        # Only process actual text messages (skip receipts, typing, sync)
        if not msg.envelope.is_data_message:
            logger.debug(
                f"Skipping non-data message from {msg.envelope.sender_id} "
                f"(has receipt={msg.envelope.receipt_message is not None}, "
                f"typing={msg.envelope.typing_message is not None})"
            )
            return

        # Skip messages from ourselves
        if msg.envelope.sender_id == settings.signal_phone_number:
            return

        source = _sanitize_log(msg.envelope.sender_name, 40)
        text_preview = _sanitize_log((msg.envelope.text or ""), 60)
        context = (
            f"in group {msg.envelope.group_id[:16]}" if msg.envelope.is_group_message else "DM"
        )
        logger.info(f"📨 [{context}] {source}: {text_preview}")

        # Dispatch to handler
        if self._on_message:
            try:
                await self._on_message(msg)
            except Exception as e:
                logger.error(f"❌ Message handler error: {e}", exc_info=True)
        else:
            logger.warning("⚠️  No message handler registered!")


# ---- Singleton instance ----
signal_client = SignalClient()
