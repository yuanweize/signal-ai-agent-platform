"""
Prompt manager handles prompt template retrieval, versioning, and activation.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.versions import DEFAULT_PROMPT_VERSION, DEFAULT_SYSTEM_PROMPT_TEMPLATE
from app.models.ai import PromptVersion
from app.models.config import BotConfig
from app.services.runtime_config import DEFAULT_AI_PROMPT, KEY_AI_PROMPT


class PromptManager:
    """
    Manages versioned system prompt templates.

    Precedence:
    1. Active PromptVersion record in DB
    2. Legacy/runtime ai_prompt from BotConfig (if customized)
    3. DEFAULT_SYSTEM_PROMPT_TEMPLATE
    """

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
        if active and active.template:
            return active.template, active.version

        # Fallback to runtime BotConfig ai_prompt
        cfg_res = await session.execute(
            select(BotConfig.value).where(BotConfig.key == KEY_AI_PROMPT)
        )
        cfg_val = cfg_res.scalar_one_or_none()
        if cfg_val and cfg_val.strip() and cfg_val.strip() != DEFAULT_AI_PROMPT:
            return cfg_val.strip(), "legacy_config"

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
        now = datetime.now(UTC).replace(tzinfo=None)
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
            activated_at=now if set_active else None,
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
        now = datetime.now(UTC).replace(tzinfo=None)
        stmt = select(PromptVersion)
        res = await session.execute(stmt)
        target = None
        for item in res.scalars().all():
            if item.version == version:
                item.is_active = True
                item.activated_at = now
                target = item
            else:
                item.is_active = False

        if target:
            await session.commit()
            await session.refresh(target)
        return target


prompt_manager = PromptManager()
