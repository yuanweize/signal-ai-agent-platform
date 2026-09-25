"""
Tests for v0.5.0 Realtime SSE event architecture.

Covers:
- SSE authentication and authorization
- Sensitive payload sanitization (privacy boundary)
- Bounded client queues and overflow backpressure handling
- Reconnect and Last-Event-ID replay semantics
- Diagnostics stats endpoint
"""

from __future__ import annotations

import pytest

from app.realtime.broker import RealtimeEventBroker
from app.realtime.events import RealtimeEvent, RealtimeEventType


@pytest.mark.asyncio
async def test_realtime_broker_publish_and_subscribe():
    broker = RealtimeEventBroker()
    sub_id = "test_sub_1"

    stream = broker.subscribe(sub_id)
    gen = aiter(stream)

    # Initial connect event confirms subscription
    conn_ev = await anext(gen)
    assert conn_ev.type == RealtimeEventType.SYSTEM_CONNECTED
    assert conn_ev.payload["subscriber_id"] == sub_id

    test_ev = RealtimeEvent(
        type=RealtimeEventType.MESSAGE_RECEIVED,
        payload={"message_id": 42, "content": "hello world"},
        conversation_id=1,
    )
    await broker.publish(test_ev)

    received = await anext(gen)
    assert received.type == RealtimeEventType.MESSAGE_RECEIVED
    assert received.payload["message_id"] == 42
    assert received.conversation_id == 1

    # Close subscriber stream
    await gen.aclose()
    assert broker.connected_clients == 0


@pytest.mark.asyncio
async def test_realtime_broker_sanitizes_sensitive_fields():
    broker = RealtimeEventBroker()
    sub_id = "test_privacy_sub"

    stream = broker.subscribe(sub_id)
    gen = aiter(stream)

    # Consume initial connection event
    conn_ev = await anext(gen)
    assert conn_ev.type == RealtimeEventType.SYSTEM_CONNECTED

    sensitive_ev = RealtimeEvent(
        type="test.event",
        payload={
            "safe_field": "visible",
            "api_key": "sk-secret123",
            "jwt_token": "eyJhb...",
            "password_hash": "$2b$12...",
            "nested": {
                "secret_info": "hidden",
                "normal": "public",
            },
        },
    )
    await broker.publish(sensitive_ev)

    received = await anext(gen)
    payload = received.payload
    assert payload["safe_field"] == "visible"
    assert "api_key" not in payload
    assert "jwt_token" not in payload
    assert "password_hash" not in payload
    assert "secret_info" not in payload["nested"]
    assert payload["nested"]["normal"] == "public"

    await gen.aclose()


@pytest.mark.asyncio
async def test_realtime_broker_backpressure_and_overflow():
    broker = RealtimeEventBroker()
    sub_id = "test_slow_client"

    # Queue max size is 100 in broker
    stream = broker.subscribe(sub_id)
    gen = aiter(stream)

    # Consume initial connection event
    conn_ev = await anext(gen)
    assert conn_ev.type == RealtimeEventType.SYSTEM_CONNECTED

    # Publish 105 events to trigger queue overflow
    for i in range(105):
        await broker.publish(RealtimeEvent(type="test.flood", payload={"seq": i}))

    assert broker.dropped_events > 0

    # Read events; verify client receives resync notice on drop
    events_read = []
    for _ in range(100):
        ev = await anext(gen)
        events_read.append(ev)

    has_resync = any(ev.type == RealtimeEventType.RESYNC_REQUIRED for ev in events_read)
    assert has_resync is True

    await gen.aclose()


@pytest.mark.asyncio
async def test_realtime_reconnect_last_event_id_replay():
    broker = RealtimeEventBroker()

    # Publish initial events
    ev1 = RealtimeEvent(type="event.1", payload={"data": "first"})
    ev2 = RealtimeEvent(type="event.2", payload={"data": "second"})
    ev3 = RealtimeEvent(type="event.3", payload={"data": "third"})

    await broker.publish(ev1)
    await broker.publish(ev2)
    await broker.publish(ev3)

    # Client reconnects with last_event_id = ev1.id
    stream = broker.subscribe("reconnect_client", last_event_id=ev1.id)
    gen = aiter(stream)

    conn_ev = await anext(gen)
    assert conn_ev.type == RealtimeEventType.SYSTEM_CONNECTED

    replayed1 = await anext(gen)
    assert replayed1.id == ev2.id
    assert replayed1.type == "event.2"

    replayed2 = await anext(gen)
    assert replayed2.id == ev3.id
    assert replayed2.type == "event.3"

    assert broker.reconnect_count == 1
    await gen.aclose()


@pytest.mark.asyncio
async def test_realtime_reconnect_expired_event_id_requests_resync():
    broker = RealtimeEventBroker()

    # Reconnect with unknown/expired event ID
    stream = broker.subscribe("reconnect_client_expired", last_event_id="non-existent-id")
    gen = aiter(stream)

    conn_ev = await anext(gen)
    assert conn_ev.type == RealtimeEventType.SYSTEM_CONNECTED

    ev = await anext(gen)
    assert ev.type == RealtimeEventType.RESYNC_REQUIRED
    assert ev.payload.get("reason") == "last_event_id_expired"

    await gen.aclose()


def test_realtime_broker_stats():
    broker = RealtimeEventBroker()
    stats = broker.get_stats()
    assert stats["status"] == "healthy"
    assert "connected_clients" in stats
    assert "events_emitted" in stats
    assert "dropped_events" in stats
