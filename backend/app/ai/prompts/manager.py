"""
Prompt manager handles prompt template retrieval, versioning, and activation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.versions import DEFAULT_PROMPT_VERSION, DEFAULT_SYSTEM_PROMPT_TEMPLATE
from app.models.ai import PromptVersion


class PromptManager:
    """Manages versioned system prompt templates."""

    async def get_active_prompt(self, session: AsyncSession) -> tuple[str, str]:
        """Return (template, version) for the currently active prompt."""
        stmt = (
            select(PromptVersion)
            .where(PromptVersion.is_active.is_(True))
            .order_by(desc(PromptVersion.created_at))
            .limit(1)
        )
        result = await session.execute(stmt)
        active = result.scalar_one_or_none()
        if active:
            return active.template, active.version
        return DEFAULT_SYSTEM_PROMPT_TEMPLATE, DEFAULT_PROMPT_VERSION

    async def list_versions(self, session: AsyncSession) -> list[PromptVersion]:
        """List all prompt versions ordered by creation time descending."""
        stmt = select(PromptVersion).order_by(desc(PromptVersion.created_at))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create_version(
        self,
        session: AsyncSession,
        version: str,
        name: str,
        template: str,
        created_by: str = "admin",
        set_active: bool = False,
    ) -> PromptVersion:
        """Create a new prompt version and optionally set it as active."""
        if set_active:
            # Deactivate any currently active prompt
            stmt = select(PromptVersion).where(PromptVersion.is_active.is_(True))
            existing_active = await session.execute(stmt)
            for item in existing_active.scalars().all():
                item.is_active = False

        pv = PromptVersion(
            version=version,
            name=name,
            template=template,
            created_by=created_by,
            is_active=set_active,
            activated_at=datetime.utcnow() if set_active else None,
        )
        session.add(pv)
        await session.commit()
        await session.refresh(pv)
        return pv

    async def activate_version(
        self,
        session: AsyncSession,
        version: str,
    ) -> PromptVersion | None:
        """Activate a specific prompt version by its version string."""
        stmt = select(PromptVersion)
        res = await session.execute(stmt)
        target = None
        for item in res.scalars().all():
            if item.version == version:
                item.is_active = True
                item.activated_at = datetime.utcnow()
                target = item
            else:
                item.is_active = False

        if target:
            await session.commit()
            await session.refresh(target)
        return target


prompt_manager = PromptManager()
