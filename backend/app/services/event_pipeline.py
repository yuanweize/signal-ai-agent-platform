"""
Signal Ingestion & Event Pipeline.

Decouples WebSocket / HTTP ingestion from business processing (DB / AI / Outbound).
Guarantees:
1. Bounded queue with backpressure (never runs out of memory).
2. Worker pool with isolated errors (one failure doesn't crash the listener).
3. Per-conversation partition locking (strict ordering within same conversation,
   concurrency across different conversations).
4. Graceful shutdown and queue observability metrics.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from app.schemas.signal import SignalIncomingMessage

logger = logging.getLogger("event.pipeline")


@dataclass
class PipelineMetrics:
    events_received: int = 0
    events_processed: int = 0
    events_dropped: int = 0
    worker_errors: int = 0

    @property
    def queue_depth(self) -> int:
        return 0


class EventPipeline:
    """Bounded, partitioned event pipeline for Signal messages."""

    def __init__(
        self,
        worker_count: int = 4,
        max_queue_size: int = 1000,
        queue_capacity: int | None = None,
        num_workers: int | None = None,
        handler: Callable[[SignalIncomingMessage], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.worker_count = num_workers if num_workers is not None else worker_count
        self.max_queue_size = queue_capacity if queue_capacity is not None else max_queue_size
        self._handler = handler
        self._queue: asyncio.Queue[SignalIncomingMessage] = asyncio.Queue(
            maxsize=self.max_queue_size
        )
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        self._locks_mutex = asyncio.Lock()
        self.metrics = PipelineMetrics()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    def set_handler(
        self, handler: Callable[[SignalIncomingMessage], Coroutine[Any, Any, None]]
    ) -> None:
        self._handler = handler

    def register_handler(
        self, handler: Callable[[SignalIncomingMessage], Coroutine[Any, Any, None]]
    ) -> None:
        self.set_handler(handler)

    def get_metrics(self) -> dict[str, int]:
        return {
            "events_received": self.metrics.events_received,
            "events_enqueued": self.metrics.events_received - self.metrics.events_dropped,
            "events_processed": self.metrics.events_processed,
            "events_dropped": self.metrics.events_dropped,
            "worker_errors": self.metrics.worker_errors,
            "queue_depth": self.queue_depth,
        }

    async def start(self) -> None:
        """Start the background worker pool."""
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i), name=f"event-worker-{i}")
            for i in range(self.worker_count)
        ]
        logger.info(
            f"🚀 EventPipeline started with {self.worker_count} workers (max_queue={self.max_queue_size})"
        )

    async def stop(self, drain: bool = True) -> None:
        """Stop workers gracefully, optionally draining remaining events."""
        if not self._running:
            return
        self._running = False

        if drain and not self._queue.empty():
            logger.info(f"⏳ Draining {self._queue.qsize()} remaining events from pipeline...")
            try:
                await asyncio.wait_for(self._queue.join(), timeout=5.0)
            except TimeoutError:
                logger.warning("⚠️ Pipeline drain timed out")

        for w in self._workers:
            w.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("🛑 EventPipeline stopped")

    async def enqueue(self, msg: SignalIncomingMessage) -> bool:
        """
        Non-blocking or fast enqueue of an incoming Signal message.
        Returns True if queued, False if dropped due to full queue.
        """
        self.metrics.events_received += 1
        try:
            self._queue.put_nowait(msg)
            return True
        except asyncio.QueueFull:
            self.metrics.events_dropped += 1
            logger.warning(
                "🚨 EventPipeline queue full! Dropping inbound message under backpressure."
            )
            return False

    async def _get_conversation_lock(self, partition_key: str) -> asyncio.Lock:
        async with self._locks_mutex:
            if partition_key not in self._conversation_locks:
                self._conversation_locks[partition_key] = asyncio.Lock()
            return self._conversation_locks[partition_key]

    async def _worker_loop(self, worker_id: int) -> None:
        logger.debug(f"Worker {worker_id} started")
        while self._running:
            try:
                msg = await self._queue.get()
            except asyncio.CancelledError:
                break

            try:
                # Partition by group_id or sender_id to ensure per-conversation ordering
                envelope = msg.envelope
                partition_key = envelope.group_id or envelope.sender_id or "default"
                lock = await self._get_conversation_lock(partition_key)

                async with lock:
                    if self._handler:
                        await self._handler(msg)
                    else:
                        logger.warning("⚠️ No handler set on EventPipeline")

                self.metrics.events_processed += 1
            except Exception as e:
                self.metrics.worker_errors += 1
                logger.error(f"❌ Error processing event in worker {worker_id}: {e}", exc_info=True)
            finally:
                self._queue.task_done()

        logger.debug(f"Worker {worker_id} exited")


event_pipeline = EventPipeline()
