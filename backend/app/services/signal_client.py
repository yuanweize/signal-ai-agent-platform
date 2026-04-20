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
from typing import Callable, Awaitable

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI, WebSocketException

from app.config import settings
from app.schemas.signal import SignalIncomingMessage, SignalSendRequest
from app.services.metrics import runtime_metrics

logger = logging.getLogger("signal.client")

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
        self._http_client: httpx.AsyncClient | None = None

        # Reconnection state
        self._reconnect_delay = 1.0  # Start at 1 second
        self._max_reconnect_delay = 60.0
        self._reconnect_attempts = 0

    @property
    def on_message(self) -> MessageCallback | None:
        return self._on_message

    @on_message.setter
    def on_message(self, callback: MessageCallback) -> None:
        """Register a callback for incoming messages."""
        self._on_message = callback

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
                logger.info(
                    f"✉️  Message sent to {recipients} "
                    f"({len(text)} chars)"
                )
                return True
            else:
                logger.error(
                    f"❌ Send failed: HTTP {response.status_code} — {response.text}"
                )
                return False

        except httpx.HTTPError as e:
            logger.error(f"❌ Send HTTP error: {e}")
            return False

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
        self._reconnect_delay = 1.0
        self._reconnect_attempts = 0
        self._listener_task = asyncio.create_task(self._listener_loop())
        logger.info("🎧 Signal message listener started")

    async def stop(self) -> None:
        """Stop the background message listener gracefully."""
        self._running = False

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

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
                logger.warning(
                    f"⚠️  WebSocket connection failed: {e.__class__.__name__}: {e}"
                )
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
                delay = min(
                    self._reconnect_delay * (2 ** min(self._reconnect_attempts - 1, 6)),
                    self._max_reconnect_delay,
                )
                logger.info(
                    f"⏳ Reconnecting in {delay:.0f}s "
                    f"(attempt {self._reconnect_attempts})..."
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
        ) as ws:
            # Reset backoff on successful connection
            self._reconnect_delay = 1.0
            self._reconnect_attempts = 0
            logger.info("✅ WebSocket connected — listening for messages")

            async for raw_message in ws:
                if not self._running:
                    break
                await self._process_raw_message(raw_message)

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
                    empty_polls += 1
                else:
                    runtime_metrics.inc("signal.pull.fail")
                    if response.status_code == 401:
                        runtime_metrics.inc("signal.pull.401")
                    if response.status_code >= 500:
                        runtime_metrics.inc("signal.pull.5xx")
                    logger.warning(
                        f"⚠️  Poll response: HTTP {response.status_code}"
                    )
                    empty_polls += 1

            except httpx.HTTPError as e:
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

        source = msg.envelope.sender_name
        text_preview = (msg.envelope.text or "")[:60]
        context = f"in group {msg.envelope.group_id}" if msg.envelope.is_group_message else "DM"
        logger.info(f"📨 [{context}] {source}: {text_preview}")

        # Dispatch to handler
        if self._on_message:
            try:
                await self._on_message(msg)
            except Exception as e:
                logger.error(
                    f"❌ Message handler error: {e}", exc_info=True
                )
        else:
            logger.warning("⚠️  No message handler registered!")


# ---- Singleton instance ----
signal_client = SignalClient()
