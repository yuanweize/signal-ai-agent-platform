"""
Memory provider abstractions and NativeMemoryProvider implementation.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import MemoryItem

logger = logging.getLogger("ai.memory")


@runtime_checkable
class MemoryProvider(Protocol):
    """Protocol for scoped durable memory management."""

    async def search(
        self,
        session: AsyncSession,
        scope_type: str,
        scope_id: str,
        query: str | None = None,
        limit: int = 5,
    ) -> list[MemoryItem]:
        """Search memories scoped to a specific user, group, or global scope."""
        ...

    async def add(
        self,
        session: AsyncSession,
        scope_type: str,
        scope_id: str,
        content: str,
        memory_type: str = "fact",
        importance: int = 3,
        source_conversation_id: int | None = None,
        created_by: str = "ai_extraction",
    ) -> MemoryItem:
        """Add a memory item."""
        ...

    async def delete(self, session: AsyncSession, memory_id: int) -> bool:
        """Delete a memory item."""
        ...


class NativeMemoryProvider:
    """Database-backed scoped memory provider."""

    async def search(
        self,
        session: AsyncSession,
        scope_type: str,
        scope_id: str,
        query: str | None = None,
        limit: int = 5,
    ) -> list[MemoryItem]:
        stmt = (
            select(MemoryItem)
            .where(
                MemoryItem.scope_type == scope_type,
                MemoryItem.scope_id == str(scope_id),
                MemoryItem.status.in_(["active", "pinned"]),
            )
            .order_by(desc(MemoryItem.importance), desc(MemoryItem.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        items = list(result.scalars().all())

        if query and query.strip() and items:
            q_words = [w.lower() for w in query.split() if len(w) > 2]
            if q_words:

                def score(item: MemoryItem) -> int:
                    text = item.content.lower()
                    return sum(1 for w in q_words if w in text)

                items.sort(key=score, reverse=True)

        return items[:limit]

    async def add(
        self,
        session: AsyncSession,
        scope_type: str,
        scope_id: str,
        content: str,
        memory_type: str = "fact",
        importance: int = 3,
        source_conversation_id: int | None = None,
        created_by: str = "ai_extraction",
    ) -> MemoryItem:
        item = MemoryItem(
            scope_type=scope_type,
            scope_id=str(scope_id),
            content=content,
            memory_type=memory_type,
            importance=importance,
            source_conversation_id=source_conversation_id,
            created_by=created_by,
            status="active",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        logger.info(f"Saved memory item #{item.id} for {scope_type}:{scope_id}")
        return item

    async def delete(self, session: AsyncSession, memory_id: int) -> bool:
        res = await session.execute(delete(MemoryItem).where(MemoryItem.id == memory_id))
        await session.commit()
        if res.rowcount > 0:
            logger.info(f"Purged memory item #{memory_id}")
            return True
        return False
