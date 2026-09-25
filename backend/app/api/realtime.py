"""Realtime Server-Sent Events (SSE) router."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from app.api.deps import AdminUser, get_current_admin
from app.realtime.broker import event_broker

logger = logging.getLogger("app.api.realtime")

router = APIRouter(prefix="/realtime", tags=["Realtime"])


@router.get("/events")
async def stream_realtime_events(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """
    Authenticated Server-Sent Events stream for realtime UI invalidation.
    Accepts Bearer authentication and optional Last-Event-ID for replay.
    """
    subscriber_id = f"{admin.username}_{uuid.uuid4().hex[:8]}"

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in event_broker.subscribe(
                subscriber_id=subscriber_id,
                last_event_id=last_event_id,
            ):
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                yield event.to_sse()
        except Exception as e:
            logger.debug(f"Client {subscriber_id} stream ended: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stats")
async def get_realtime_stats(
    admin: AdminUser = Depends(get_current_admin),
) -> dict:
    """Return operational diagnostics for the realtime broker."""
    return event_broker.get_stats()
