"""In-memory event broker for Server-Sent Events with bounded queues and replay."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator

from app.realtime.events import RealtimeEvent, RealtimeEventType

logger = logging.getLogger("app.realtime.broker")

# Bounded queue size per subscriber
MAX_CLIENT_QUEUE_SIZE = 100
# Replay buffer capacity for reconnecting clients
MAX_REPLAY_BUFFER_SIZE = 150


class RealtimeSubscription:
    """Represents an active SSE subscriber connection."""

    def __init__(self, subscriber_id: str, queue: asyncio.Queue[RealtimeEvent]) -> None:
        self.subscriber_id = subscriber_id
        self.queue = queue
        self.is_active = True


class RealtimeEventBroker:
    """
    Central event broker distributing events to connected administrators.
    Provides backpressure safety, replay buffer for reconnects, and lifecycle metrics.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue[RealtimeEvent]] = {}
        self._replay_buffer: deque[RealtimeEvent] = deque(maxlen=MAX_REPLAY_BUFFER_SIZE)
        self._lock = asyncio.Lock()

        # Telemetry metrics
        self.events_emitted: int = 0
        self.dropped_events: int = 0
        self.reconnect_count: int = 0

    @property
    def connected_clients(self) -> int:
        return len(self._subscribers)

    def _sanitize_payload(self, payload: dict) -> dict:
        """Strip sensitive fields before broadcasting."""
        clean = {}
        sensitive_keys = {
            "password",
            "password_hash",
            "token",
            "api_key",
            "secret",
            "enc_key",
            "jwt",
            "authorization",
        }
        for k, v in payload.items():
            if any(s in k.lower() for s in sensitive_keys):
                continue
            if isinstance(v, dict):
                clean[k] = self._sanitize_payload(v)
            else:
                clean[k] = v
        return clean

    async def publish(self, event: RealtimeEvent) -> None:
        """Broadcast an event to all connected subscribers."""
        # Sanitize payload
        clean_payload = self._sanitize_payload(event.payload)
        safe_event = RealtimeEvent(
            id=event.id,
            type=event.type,
            payload=clean_payload,
            timestamp=event.timestamp,
            scope=event.scope,
            conversation_id=event.conversation_id,
        )

        async with self._lock:
            self._replay_buffer.append(safe_event)
            self.events_emitted += 1

            for sub_id, queue in list(self._subscribers.items()):
                try:
                    if queue.full():
                        # Queue overflow: drop oldest to prevent memory explosion
                        try:
                            queue.get_nowait()
                            self.dropped_events += 1
                        except asyncio.QueueEmpty:
                            pass
                        # Push a resync notice so client knows an event was lost
                        resync_ev = RealtimeEvent(
                            type=RealtimeEventType.RESYNC_REQUIRED,
                            payload={"reason": "queue_overflow"},
                            scope=safe_event.scope,
                        )
                        try:
                            queue.put_nowait(resync_ev)
                        except asyncio.QueueFull:
                            pass
                    queue.put_nowait(safe_event)
                except Exception as e:
                    logger.warning(f"Failed to enqueue event for subscriber {sub_id}: {e}")

    async def subscribe(
        self,
        subscriber_id: str,
        last_event_id: str | None = None,
    ) -> AsyncIterator[RealtimeEvent]:
        """
        Subscribe to event stream. Replays missed events if last_event_id is present.
        Yields events as they arrive until client disconnects.
        """
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=MAX_CLIENT_QUEUE_SIZE)

        async with self._lock:
            self._subscribers[subscriber_id] = queue

            # Handle reconnection with Last-Event-ID replay
            if last_event_id:
                self.reconnect_count += 1
                replay_events = list(self._replay_buffer)
                found = False
                missed: list[RealtimeEvent] = []
                for ev in replay_events:
                    if found:
                        missed.append(ev)
                    elif ev.id == last_event_id:
                        found = True

                if found:
                    for ev in missed:
                        queue.put_nowait(ev)
                else:
                    # Event ID is too old or unknown: tell client to full-resync
                    resync_ev = RealtimeEvent(
                        type=RealtimeEventType.RESYNC_REQUIRED,
                        payload={"reason": "last_event_id_expired"},
                    )
                    queue.put_nowait(resync_ev)

        logger.info(f"SSE client {subscriber_id} connected (total: {self.connected_clients})")

        # Emit immediate connection confirmation event
        yield RealtimeEvent(
            type=RealtimeEventType.SYSTEM_CONNECTED,
            payload={"subscriber_id": subscriber_id, "clients": self.connected_clients},
        )

        try:
            while True:
                # 15-second timeout for keepalive heartbeat
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event
                except TimeoutError:
                    # Emit heartbeat keep-alive
                    yield RealtimeEvent(
                        type=RealtimeEventType.SYSTEM_HEARTBEAT,
                        payload={"clients": self.connected_clients},
                    )
        finally:
            async with self._lock:
                self._subscribers.pop(subscriber_id, None)
            logger.info(
                f"SSE client {subscriber_id} disconnected (total: {self.connected_clients})"
            )

    def get_stats(self) -> dict[str, int | str]:
        """Return operational health diagnostics."""
        return {
            "status": "healthy",
            "connected_clients": self.connected_clients,
            "events_emitted": self.events_emitted,
            "dropped_events": self.dropped_events,
            "reconnect_count": self.reconnect_count,
            "replay_buffer_size": len(self._replay_buffer),
        }


# Global broker singleton
event_broker = RealtimeEventBroker()
